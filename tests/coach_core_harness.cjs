// Test harness for tools/coach_page/core.js (estebanmoreno04 fork).
// Usage: node tests/coach_core_harness.cjs <coach.html> -> prints JSON results.
const fs = require("fs");
const path = require("path");
const html = fs.readFileSync(process.argv[2], "utf8");
const match = html.match(/const DATA = (\{[\s\S]*?\});\s*\n\s*const core =/);
if (!match) throw new Error("embedded data not found");
const DATA = JSON.parse(match[1]); // "<\/" is a valid JSON escape
const coreSource = fs.readFileSync(path.join(__dirname, "..", "tools", "coach_page", "core.js"), "utf8");
const mod = { exports: {} };
new Function("module", coreSource)(mod);
const core = mod.exports;
let calc = null;
try { calc = require(path.join(__dirname, "..", "tools", "calc", "node_modules", "@smogon", "calc")); } catch (e) { calc = null; }
const coach = core.create(DATA, calc);
const safe = (fn) => { try { return fn(); } catch (e) { return { error: e.message }; } };
const team = fs.readFileSync(0, "utf8");
const out = {
  status: coach.status(Date.parse(DATA.snapshot.generated_at)),
  usage: coach.usage("in_person", 3),
  resolve: ["Mega Charizard Y", "charizard-mega-y", "Basculegion-F", "Incineroarr", "Kommo-o"].map((n) => safe(() => coach.resolveSpecies(n))),
  unknown: safe(() => coach.resolveSpecies("Pikachuuuu")),
  pokemon: safe(() => { const p = coach.pokemon("Kingambit"); return { name: p.name, ip: p.in_person, items: p.sets && p.sets.items, best: p.best_matchups.length, top_cut: p.top_cut_teams }; }),
  team: safe(() => coach.analyzeTeam(team)),
  calc: calc ? safe(() => coach.calcDamage({ attacker: { species: "Charizard", item: "Charizardite Y", nature: "Modest", stat_points: { spa: 32 } }, defender: { species: "Kingambit", nature: "Adamant", stat_points: { hp: 32 } }, move: "Heat Wave", weather: "sun" })) : "calc not installed",
  speed: calc ? safe(() => coach.calcSpeed({ a: { species: "Whimsicott", nature: "Timid", stat_points: { spe: 32 }, tailwind: true }, b: { species: "Garchomp", nature: "Jolly", stat_points: { spe: 32 }, boosts: { spe: 1 } } })) : "calc not installed",
  trend: safe(() => coach.trend(3)),
  event: safe(() => { const e = coach.eventUsage(coach.byEvent.length ? coach.shortEvent(coach.byEvent[0].name) : "x", 3); return { name: e.name, usage: e.usage, top_cut: e.top_cut.length }; }),
  latest: safe(() => coach.eventUsage("ultimo", 1).name),
  missing_event: safe(() => coach.eventUsage("Atlantis", 1)),
  pokemon_by_event: safe(() => coach.pokemon("Incineroar").by_event),
  series: safe(() => coach.regionalSeries([coach.usageRows[0].species, "not-a-species"], 5)),
  series_day2: safe(() => coach.regionalSeries([coach.usageRows[0].species], 5, "day2_share")),
  unproven: calc ? safe(() => coach.calcDamage({ attacker: { species: "Incineroar" }, defender: { species: "Charizard" }, move: "Thunder Punch" }).notes) : "calc not installed",
  types: calc ? safe(() => coach.typeMatchup("Mega Charizard Y", "Kingambit")) : "calc not installed",
  tools: coach.tools().map((t) => t.name),
  instructions_bytes: Buffer.byteLength(coach.instructions(true)),
};
process.stdout.write(JSON.stringify(out));
