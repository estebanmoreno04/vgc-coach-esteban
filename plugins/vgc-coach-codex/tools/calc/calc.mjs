// Damage and speed calc bridge for vgc-coach (estebanmoreno04 fork of
// NoahJenkins/vgc-coach). Reads one JSON request on stdin, runs @smogon/calc
// with Pokemon Champions mechanics (generation 0: level 50, stat points in the
// `evs` field, Champions damage modifiers) and prints one JSON result.
//
// Request: { calc_type, move, is_crit, attacker, defender, field }
//   side: { species, ability, item, nature, evs:{hp,atk,def,spa,spd,spe},
//           boosts:{atk,def,spa,spd,spe}, status, current_hp_percent }
//   field: { format, weather, terrain, attacker_side:{...}, defender_side:{...} }
//   side flags: helping_hand, tailwind, reflect, light_screen, aurora_veil, friend_guard

import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const calc = require("@smogon/calc");
const { getFinalSpeed } = require("@smogon/calc/dist/mechanics/util");

const GEN_CHAMPIONS = 0;
const STATUS = { healthy: "", burned: "brn", paralyzed: "par", poisoned: "psn", badly_poisoned: "tox", asleep: "slp", frozen: "frz" };
const WEATHER = { none: undefined, sun: "Sun", rain: "Rain", sand: "Sand", snow: "Snow", "harsh sunshine": "Harsh Sunshine", "heavy rain": "Heavy Rain" };
const TERRAIN = { none: undefined, electric: "Electric", grassy: "Grassy", psychic: "Psychic", misty: "Misty" };

function read(stream) {
  return new Promise((resolve, reject) => {
    let data = "";
    stream.setEncoding("utf8");
    stream.on("data", (chunk) => { data += chunk; });
    stream.on("end", () => resolve(data));
    stream.on("error", reject);
  });
}

function lookup(table, value, label) {
  const key = String(value ?? "none").trim().toLowerCase();
  if (!(key in table)) throw new Error(`unsupported ${label}: ${value}`);
  return table[key];
}

const toID = (text) => String(text).toLowerCase().replace(/[^a-z0-9]+/g, "");

function pokemon(gen, side) {
  if (!side || !side.species) throw new Error("both sides need a species");
  if (!gen.species.get(toID(side.species))) throw new Error(`unknown species: ${side.species}`);
  const options = {
    level: 50,
    nature: side.nature || "Hardy",
    evs: side.evs || {},
    boosts: side.boosts || {},
    status: lookup(STATUS, side.status || "healthy", "status"),
  };
  if (side.ability) options.ability = side.ability;
  if (side.item) options.item = side.item;
  const mon = new calc.Pokemon(gen, side.species, options);
  if (!mon.species || !mon.species.baseStats) throw new Error(`unknown species: ${side.species}`);
  if (side.current_hp_percent !== null && side.current_hp_percent !== undefined) {
    mon.originalCurHP = Math.max(1, Math.floor((mon.maxHP() * Number(side.current_hp_percent)) / 100));
  }
  return mon;
}

function sideFlags(flags = {}) {
  return {
    isHelpingHand: Boolean(flags.helping_hand),
    isTailwind: Boolean(flags.tailwind),
    isReflect: Boolean(flags.reflect),
    isLightScreen: Boolean(flags.light_screen),
    isAuroraVeil: Boolean(flags.aurora_veil),
    isFriendGuard: Boolean(flags.friend_guard),
  };
}

function stats(mon) {
  return { hp: mon.maxHP(), atk: mon.stats.atk, def: mon.stats.def, spa: mon.stats.spa, spd: mon.stats.spd, spe: mon.stats.spe };
}

function run(request) {
  const gen = calc.Generations.get(GEN_CHAMPIONS);
  const field = new calc.Field({
    gameType: String(request.field?.format || "Doubles").toLowerCase() === "singles" ? "Singles" : "Doubles",
    weather: lookup(WEATHER, request.field?.weather, "weather"),
    terrain: lookup(TERRAIN, request.field?.terrain, "terrain"),
    attackerSide: sideFlags(request.field?.attacker_side),
    defenderSide: sideFlags(request.field?.defender_side),
  });
  const attacker = pokemon(gen, request.attacker);
  const defender = pokemon(gen, request.defender);
  const base = {
    engine: `@smogon/calc ${calc.Generations ? "0.12.0" : "unknown"}`,
    mechanics: "Pokemon Champions (generation 0)",
    attacker: { species: attacker.name, stats: stats(attacker) },
    defender: { species: defender.name, stats: stats(defender) },
  };
  if (request.calc_type === "speed") {
    const attackerSpeed = getFinalSpeed(gen, attacker, field, field.attackerSide);
    const defenderSpeed = getFinalSpeed(gen, defender, field, field.defenderSide);
    return {
      ...base,
      speed: {
        attacker: attackerSpeed,
        defender: defenderSpeed,
        faster: attackerSpeed === defenderSpeed ? "tie" : attackerSpeed > defenderSpeed ? "attacker" : "defender",
      },
    };
  }
  if (!request.move) throw new Error("a move is required for damage, ko and survival calcs");
  const move = new calc.Move(gen, request.move, { isCrit: Boolean(request.is_crit) });
  if (!move.bp && move.category !== "Status" && move.name !== request.move) {
    throw new Error(`unknown move: ${request.move}`);
  }
  const result = calc.calculate(gen, attacker, defender, move, field);
  const rolls = Array.isArray(result.damage) ? result.damage.flat() : [result.damage];
  const [min, max] = result.range();
  const hp = defender.maxHP();
  const current = defender.curHP();
  let ko = null;
  try {
    ko = result.kochance();
  } catch (error) {
    ko = { chance: null, n: 0, text: "" };
  }
  return {
    ...base,
    move: { name: move.name, type: move.type, category: move.category, base_power: move.bp, spread: Boolean(move.target === "allAdjacentFoes" || move.target === "allAdjacent") },
    damage: { min, max, rolls },
    defender_hp: { max: hp, current },
    percent: { min: Math.round((1000 * min) / hp) / 10, max: Math.round((1000 * max) / hp) / 10 },
    ko: { chance: ko.chance ?? null, hits: ko.n ?? 0, text: ko.text || "" },
    description: describe(result, attacker, defender, move, max),
  };
}

// @smogon/calc throws when describing a move that does no damage (an immunity).
function describe(result, attacker, defender, move, max) {
  if (max === 0) return `${attacker.name} ${move.name} vs. ${defender.name}: no damage (immune or no effect)`;
  try {
    return result.desc();
  } catch (error) {
    return `${attacker.name} ${move.name} vs. ${defender.name}`;
  }
}

const raw = await read(process.stdin);
try {
  const output = run(JSON.parse(raw.replace(/^﻿/, "")));
  process.stdout.write(JSON.stringify({ ok: true, ...output }));
} catch (error) {
  process.stdout.write(JSON.stringify({ ok: false, error: String(error && error.message ? error.message : error) }));
  process.exitCode = 1;
}
