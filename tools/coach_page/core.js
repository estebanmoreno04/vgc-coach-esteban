// Coach page core (estebanmoreno04 fork of NoahJenkins/vgc-coach).
// Pure functions over the compact data embedded by tools/build_coach_page.py:
// name resolution, usage, species detail, matchups, top cut, team analysis
// and @smogon/calc damage/speed. Mirrors tools/vgc_data/query.py. No
// regulation is named here; everything comes from the embedded data.
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.VGCCoachCore = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";

  const SEGMENTS = ["in_person", "online", "total"];
  const MAX_AGE_DAYS = 7;

  function slug(value) {
    return String(value || "")
      .normalize("NFKD").replace(/[̀-ͯ]/g, "")
      .toLowerCase().replace(/['’.]/g, "")
      .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  }

  function pct(value) {
    return value === null || value === undefined ? null : Math.round(value * 1000) / 10;
  }

  function levenshtein(a, b) {
    const row = Array.from({ length: b.length + 1 }, (_, i) => i);
    for (let i = 1; i <= a.length; i++) {
      let prev = row[0];
      row[0] = i;
      for (let j = 1; j <= b.length; j++) {
        const tmp = row[j];
        row[j] = Math.min(row[j] + 1, row[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1));
        prev = tmp;
      }
    }
    return row[b.length];
  }

  function create(DATA, calcLib) {
    const usageRows = DATA.usage.map((r) => ({
      species: r[0], name: r[1],
      in_person: { teams: r[2], share: r[3], win_rate: r[4], day2_share: r[5], day2_conversion: r[6], top_cut_teams: r[7] },
      online: { teams: r[8], share: r[9], win_rate: r[10] },
      total: { share: r[11], win_rate: r[12] },
    }));
    const usageBy = new Map(usageRows.map((row) => [row.species, row]));
    const megas = DATA.megas.map((r) => ({ mega: r[0], name: r[1], in_person: r[2], in_person_wr: r[3], online: r[4], total: r[5] }));
    const megaBy = new Map(megas.map((row) => [row.mega, row]));
    const dex = DATA.dex || { names: {}, mega_base: {}, stones: {} };
    const display = (id) => (id ? dex.names[id] || (usageBy.get(id) || {}).name || id.split("-").map((p) => p[0].toUpperCase() + p.slice(1)).join("-") : null);
    const baseOf = (mega) => dex.mega_base[mega] || mega.split("-mega")[0];

    function megaFor(species, item) {
      if (!item || !/ite(\s+[xyz])?$/i.test(item.trim()) || slug(item) === "eviolite") return null;
      const known = dex.stones[slug(item)];
      if (known && baseOf(known) === species) return known;
      const candidates = Object.keys(dex.mega_base).filter((m) => dex.mega_base[m] === species).sort();
      const letter = (item.trim().match(/ite\s+([xyz])$/i) || [])[1];
      for (const mega of candidates) {
        const megaLetter = mega.split("-mega")[1].replace(/^-/, "") || undefined;
        if (megaLetter === (letter ? letter.toLowerCase() : undefined)) return mega;
      }
      if (candidates.length === 1) return candidates[0];
      if (!candidates.length && slug(item).slice(0, 4) === species.split("-")[0].slice(0, 4)) {
        return species.split("-")[0] + "-mega" + (letter ? "-" + letter.toLowerCase() : "");
      }
      return null;
    }

    function resolveSpecies(text) {
      let raw = String(text || "").trim();
      const mega = raw.match(/^mega\s+(.+?)(?:\s+([xyz]))?$/i);
      if (mega) raw = mega[1] + "-mega" + (mega[2] ? "-" + mega[2] : "");
      const key = slug(raw);
      if (megaBy.has(key) || dex.mega_base[key]) return { species: baseOf(key), mega: key };
      if (usageBy.has(key)) return { species: key, mega: null };
      for (const row of usageRows) if (slug(row.name) === key) return { species: row.species, mega: null };
      for (const row of megas) if (slug(row.name) === key) return { species: baseOf(row.mega), mega: row.mega };
      const candidates = [...usageBy.keys(), ...megaBy.keys()];
      const ranked = candidates.map((c) => [c, levenshtein(key, c)]).sort((a, b) => a[1] - b[1]);
      if (ranked.length && ranked[0][1] <= Math.max(1, Math.floor(key.length / 6))) {
        const best = ranked[0][0];
        return megaBy.has(best) ? { species: baseOf(best), mega: best } : { species: best, mega: null };
      }
      const hint = ranked.slice(0, 3).map((r) => display(r[0])).join(", ");
      throw new Error(`"${text}" no aparece en los datos actuales. ¿Quizá: ${hint}?`);
    }

    function status(now) {
      const reg = DATA.regulation;
      const snap = DATA.snapshot;
      const ageDays = Math.round(((now || Date.now()) - Date.parse(snap.generated_at)) / 864e5 * 10) / 10;
      const alerts = [];
      if (ageDays > MAX_AGE_DAYS) alerts.push(`Los datos tienen ${ageDays} días.`);
      if (snap.early_meta) alerts.push("Meta temprano: aún hay pocos torneos de esta regulación.");
      if (reg.window && reg.window.end && (now || Date.now()) > Date.parse(reg.window.end)) alerts.push("La ventana de esta regulación ya terminó; puede haber una nueva.");
      if (reg.confidence === "low") alerts.push("La regulación se detectó con confianza baja.");
      return {
        regulation: reg.id, label: reg.label, window: reg.window, mechanics: reg.mechanics, rules: reg.rules,
        official_url: reg.official_url, next_regulation: reg.next ? reg.next.regulation_id : null,
        snapshot_generated_at: snap.generated_at, snapshot_age_days: ageDays, data_through: snap.data_through,
        early_meta: snap.early_meta, segments: snap.segments, alerts,
      };
    }

    function usage(segment, top) {
      const seg = SEGMENTS.includes(segment) ? segment : "in_person";
      const n = Math.min(Math.max(Number(top) || 15, 1), 40);
      return usageRows
        .filter((row) => (seg === "total" ? row.total.share : row[seg].teams))
        .sort((a, b) => (b[seg].share || 0) - (a[seg].share || 0))
        .slice(0, n)
        .map((row) => ({
          name: row.name, share_pct: pct(row[seg].share), win_rate_pct: pct(row[seg].win_rate),
          in_person_day2_conversion_pct: pct(row.in_person.day2_conversion), in_person_teams: row.in_person.teams,
        }));
    }

    function pokemon(name) {
      const { species, mega } = resolveSpecies(name);
      const row = usageBy.get(species);
      if (!row) throw new Error(`Sin datos de uso para ${display(species)}.`);
      const sets = DATA.sets[species] || null;
      const partners = DATA.pairs.in_person.filter((p) => p[0].includes(species)).slice(0, 8)
        .map((p) => ({ with: p[1].find((n) => n !== row.name) || p[1][0], share_pct: pct(p[3]), win_rate_pct: pct(p[4]), teams: p[2] }));
      const records = DATA.matchups.filter((m) => m[0] === species && m[3] > 0)
        .map((m) => ({ vs: display(m[1]), win_rate_pct: pct(m[2] / m[3]), games: m[3] }))
        .sort((a, b) => b.win_rate_pct - a.win_rate_pct);
      const teams = DATA.top_cut.filter((t) => t[7].some((mon) => resolveSafe(mon[0]) === species));
      return {
        name: row.name, mega_asked: mega ? display(mega) : null,
        in_person: { share_pct: pct(row.in_person.share), win_rate_pct: pct(row.in_person.win_rate), day2_share_pct: pct(row.in_person.day2_share), day2_conversion_pct: pct(row.in_person.day2_conversion), top_cut_teams: row.in_person.top_cut_teams, teams: row.in_person.teams },
        online: { share_pct: pct(row.online.share), win_rate_pct: pct(row.online.win_rate), teams: row.online.teams },
        megas: megas.filter((m) => baseOf(m.mega) === species).map((m) => ({ name: m.name, in_person_pct: pct(m.in_person), online_pct: pct(m.online) })),
        sets: sets && {
          sample: sets.sample,
          items: sets.items.slice(0, 4).map(([n, s]) => `${n} ${pct(s)}%`),
          abilities: sets.abilities.map(([n, s]) => `${n} ${pct(s)}%`),
          natures: sets.natures.slice(0, 3).map(([n, s]) => `${n} ${pct(s)}%`),
          moves: sets.moves.slice(0, 8).map(([n, s]) => `${n} ${pct(s)}%`),
          top_sets: sets.top_sets.map(([i, a, nat, mv, s]) => `${pct(s)}%: ${i} | ${a} | ${nat} | ${mv.join(", ")}`),
        },
        partners_in_person: partners,
        best_matchups: records.slice(0, 5),
        worst_matchups: records.slice(-5).reverse(),
        matchup_basis: "team sheets (especies del equipo, no las que salieron a jugar)",
        top_cut_teams: teams.length,
        recent_top_cut: teams.slice(0, 3).map(formatTeam),
      };
    }

    function resolveSafe(name) {
      try { return resolveSpecies(name).species; } catch (e) { return slug(name); }
    }

    function formatTeam(t) {
      return {
        segment: t[0], event: t[1], date: t[2], placement: t[3], player: t[4], country: t[5], record: t[6],
        team: t[7].map(([n, item, ab, nat, moves]) => `${n} @ ${item || "?"} | ${ab || "?"} | ${nat || "?"} | ${(moves || []).join(", ")}`),
      };
    }

    function matchup(a, b) {
      const x = resolveSpecies(a).species;
      const y = resolveSpecies(b).species;
      return DATA.matchups.filter((m) => (m[0] === x && m[1] === y) || (m[0] === y && m[1] === x))
        .map((m) => ({ species: display(m[0]), vs: display(m[1]), win_rate_pct: pct(m[2] / m[3]), games: m[3] }));
    }

    function topCut(segment, species, limit) {
      const wanted = species ? resolveSpecies(species).species : null;
      return DATA.top_cut
        .filter((t) => (!segment || t[0] === segment) && (!wanted || t[7].some((mon) => resolveSafe(mon[0]) === wanted)))
        .slice(0, Math.min(Math.max(Number(limit) || 6, 1), 12))
        .map(formatTeam);
    }

    function parseTeam(text) {
      const header = /^([^@(]+?)(?:\s*\(([^)]+)\))?(?:\s*\([MF]\))?\s*(?:@\s*(.+))?$/;
      const lines = String(text || "").replace(/\r/g, "").split("\n").map((l) => l.trim());
      const mons = [];
      if (lines.some((l) => l.includes("|"))) {
        for (const line of lines) {
          if (!line.includes("|")) continue;
          const parts = line.split("|").map((p) => p.trim());
          const h = parts[0].match(header);
          mons.push({
            name: h ? (h[2] || h[1]).trim() : parts[0],
            item: h && h[3] ? h[3].trim() : null,
            ability: parts[1] || null,
            nature: parts[2] || null,
            moves: parts.slice(3).join(",").split(",").map((m) => m.trim()).filter(Boolean),
          });
        }
        return mons;
      }
      let cur = null;
      for (const line of [...lines, ""]) {
        if (!line) { if (cur) mons.push(cur); cur = null; continue; }
        if (!cur) {
          const h = line.match(header);
          cur = { name: h ? (h[2] || h[1]).trim() : line, item: h && h[3] ? h[3].trim() : null, ability: null, nature: null, moves: [] };
        } else if (/^ability:/i.test(line)) cur.ability = line.split(":").slice(1).join(":").trim();
        else if (/ nature$/i.test(line)) cur.nature = line.replace(/ nature$/i, "").trim();
        else if (line.startsWith("-")) cur.moves.push(line.replace(/^-\s*/, ""));
      }
      return mons;
    }

    function analyzeTeam(text) {
      const parsed = parseTeam(text);
      if (!parsed.length) throw new Error("No he podido leer ningún Pokémon del equipo.");
      const members = [];
      for (const mon of parsed) {
        let species;
        try { species = resolveSpecies(mon.name).species; } catch (e) { members.push({ input: mon.name, error: e.message }); continue; }
        const row = usageBy.get(species);
        const sets = DATA.sets[species];
        const notes = [];
        if (sets) {
          const common = new Set(sets.moves.map(([n]) => slug(n)));
          const rare = mon.moves.filter((m) => !common.has(slug(m)));
          if (rare.length) notes.push("movimientos poco comunes en esta especie: " + rare.join(", "));
          if (mon.item && !sets.items.some(([n]) => slug(n) === slug(mon.item))) notes.push(`objeto poco común (${mon.item})`);
        }
        members.push({
          name: display(species), mega: display(megaFor(species, mon.item)),
          in_person_share_pct: row ? pct(row.in_person.share) : null, in_person_win_rate_pct: row ? pct(row.in_person.win_rate) : null,
          day2_conversion_pct: row ? pct(row.in_person.day2_conversion) : null, online_share_pct: row ? pct(row.online.share) : null,
          common_set: sets && sets.top_sets[0] ? `${sets.top_sets[0][0]} | ${sets.top_sets[0][1]} | ${sets.top_sets[0][2]} | ${sets.top_sets[0][3].join(", ")}` : null,
          notes, species,
        });
      }
      const roster = new Set(members.filter((m) => m.species).map((m) => m.species));
      const cores = [...DATA.pairs.in_person, ...DATA.trios.in_person]
        .filter((c) => c[0].every((s) => roster.has(s)))
        .slice(0, 10)
        .map((c) => ({ core: c[1].join(" + "), share_pct: pct(c[3]), win_rate_pct: pct(c[4]) }));
      const tally = new Map();
      for (const [a, b, wins, games] of DATA.matchups) {
        if (roster.has(a) || !roster.has(b)) continue;
        const t = tally.get(a) || [0, 0];
        t[0] += wins; t[1] += games; tally.set(a, t);
      }
      const threats = [...tally.entries()].map(([s, [w, g]]) => ({ name: display(s), win_rate_vs_team_pct: pct(w / g), games: g }))
        .sort((x, y) => y.win_rate_vs_team_pct - x.win_rate_vs_team_pct);
      members.forEach((m) => delete m.species);
      return {
        members, cores_in_person: cores, biggest_threats: threats.slice(0, 6), most_favourable: threats.slice(-4).reverse(),
        matchup_basis: "team sheets (especies del equipo, no las que salieron a jugar)",
      };
    }

    // -- calcs ---------------------------------------------------------------

    const SP_KEYS = { hp: "hp", atk: "atk", def: "def", spa: "spa", spd: "spd", spe: "spe" };

    function buildMon(gen, side, notes) {
      if (!calcLib) throw new Error("La calculadora no ha cargado en esta página.");
      let species = String(side.species || "");
      let ability = side.ability || undefined;
      const resolved = (() => { try { return resolveSpecies(species); } catch (e) { return { species: slug(species), mega: null }; } })();
      if (resolved.mega) species = display(resolved.mega);
      else {
        const mega = megaFor(resolved.species, side.item);
        if (mega) {
          species = display(mega);
          ability = undefined;
          notes.push(`${side.species} con ${side.item} se calcula como ${species}.`);
        }
      }
      const sp = {};
      let total = 0;
      for (const [key, value] of Object.entries(side.stat_points || {})) {
        const k = SP_KEYS[key];
        const v = Number(value) || 0;
        if (!k) continue;
        if (v < 0 || v > 32) throw new Error(`Stat points fuera de rango (0-32) en ${key}.`);
        sp[k] = v; total += v;
      }
      if (total > 66) throw new Error("La suma de stat points supera 66.");
      const options = { level: 50, nature: side.nature || "Hardy", evs: sp, boosts: side.boosts || {} };
      if (ability) options.ability = ability;
      if (side.item) options.item = side.item;
      if (!gen.species.get(slug(species).replace(/-/g, ""))) throw new Error(`Especie desconocida para la calculadora: ${species}`);
      return new calcLib.Pokemon(gen, species, options);
    }

    function calcDamage(input) {
      const gen = calcLib.Generations.get(0);
      const notes = [];
      const attacker = buildMon(gen, input.attacker || {}, notes);
      const defender = buildMon(gen, input.defender || {}, notes);
      const weather = { sun: "Sun", rain: "Rain", sand: "Sand", snow: "Snow" }[String(input.weather || "").toLowerCase()];
      const terrain = { electric: "Electric", grassy: "Grassy", psychic: "Psychic", misty: "Misty" }[String(input.terrain || "").toLowerCase()];
      const side = (flags = {}) => ({ isHelpingHand: !!flags.helping_hand, isReflect: !!flags.reflect, isLightScreen: !!flags.light_screen, isAuroraVeil: !!flags.aurora_veil, isFriendGuard: !!flags.friend_guard });
      const field = new calcLib.Field({
        gameType: String(input.format || "doubles").toLowerCase() === "singles" ? "Singles" : "Doubles",
        weather, terrain, attackerSide: side(input.attacker_side), defenderSide: side(input.defender_side),
      });
      const move = new calcLib.Move(gen, String(input.move || ""), { isCrit: !!input.crit });
      const result = calcLib.calculate(gen, attacker, defender, move, field);
      const [min, max] = result.range();
      const hp = defender.maxHP();
      let ko = "";
      try { ko = result.kochance().text; } catch (e) { ko = ""; }
      return {
        summary: result.desc(), damage: [min, max], percent: [Math.round(1000 * min / hp) / 10, Math.round(1000 * max / hp) / 10],
        ko, notes, engine: "@smogon/calc, mecánica de Pokémon Champions",
      };
    }

    function calcSpeed(input) {
      const gen = calcLib.Generations.get(0);
      const notes = [];
      const speedOf = (side) => {
        const mon = buildMon(gen, side || {}, notes);
        const stage = Number((side.boosts || {}).spe) || 0;
        let speed = Math.floor(mon.stats.spe * (stage >= 0 ? (2 + stage) / 2 : 2 / (2 - stage)));
        if (/choice scarf/i.test(side.item || "")) speed = Math.floor(speed * 1.5);
        if (side.tailwind) speed *= 2;
        if (/paraly/i.test(side.status || "")) speed = Math.floor(speed / 2);
        return { name: mon.name, speed };
      };
      const a = speedOf(input.a || {});
      const b = speedOf(input.b || {});
      return { a, b, faster: a.speed === b.speed ? "empate" : a.speed > b.speed ? a.name : b.name, notes };
    }

    // -- prompt material -------------------------------------------------------

    function digest() {
      const s = status();
      const top = usage("in_person", 15).map((r, i) => `${i + 1}. ${r.name} ${r.share_pct}% (WR ${r.win_rate_pct}%, día 2 ${r.in_person_day2_conversion_pct}%)`).join("\n");
      const megaTop = megas.slice(0, 8).map((m) => `${m.name} ${pct(m.in_person)}%`).join(", ");
      return [
        `Regulación activa: ${s.label || s.regulation} (${s.regulation}), ventana ${s.window ? s.window.start : "?"} → ${s.window && s.window.end ? s.window.end : "?"}.`,
        `Mecánicas: ${(s.mechanics || []).join(", ") || "ninguna especial"}. Objetos duplicados permitidos: ${s.rules && s.rules.held_items ? s.rules.held_items.duplicates_allowed : "?"}.`,
        `Datos generados ${s.snapshot_generated_at} (hace ${s.snapshot_age_days} días), con torneos hasta ${s.data_through}. Meta temprano: ${s.early_meta ? "sí" : "no"}.`,
        `Presencial: ${s.segments.in_person.events} eventos, ${s.segments.in_person.teams} equipos (field completo), ${s.segments.in_person.day2_teams} de día 2. Online: ${s.segments.online.events} torneos, ${s.segments.online.teams} equipos.`,
        s.alerts.length ? "Avisos: " + s.alerts.join(" ") : "",
        "Top uso presencial:\n" + top,
        "Megas más usadas (presencial): " + megaTop,
      ].filter(Boolean).join("\n");
    }

    function instructions(withTools) {
      return [
        "Eres un coach de Pokémon Champions VGC (dobles) para jugadores que preparan torneos presenciales.",
        "Responde en el idioma del usuario, de forma práctica y concreta. Usa listas o tablas cortas cuando ayuden.",
        "Reglas:",
        "- Usa SOLO estos datos y lo que digan las herramientas para cifras de uso, win rate, sets, emparejamientos, top cut y cálculos. Nunca inventes números ni torneos.",
        "- Empieza las respuestas sobre meta o equipos con una línea de base de datos: regulación y fecha de los datos.",
        "- Prioriza los datos presenciales; usa online como complemento y di de qué segmento sale cada cifra.",
        "- Los emparejamientos son a nivel de team sheet (orientativos). Los stat points de los rivales no se publican: en cálculos, decláralos como supuesto.",
        "- Respeta las mecánicas de la regulación: si Terastal no está en la lista, no hables de Tera.",
        "- Si algo no está en los datos (otra regulación, un torneo posterior a la fecha de los datos), dilo claramente.",
        "- Para auditar un equipo: identidad, 2-4 hallazgos ordenados por impacto con su consecuencia en partida, cambios mínimos primero, riesgo residual.",
        "- Si te preguntan algo que no es de Pokémon VGC, responde en una frase que solo ayudas con VGC.",
        withTools
          ? "Tienes herramientas para consultar los datos (uso, Pokémon, emparejamientos, top cut, análisis de equipo, daño y velocidad). Úsalas en lugar de suponer."
          : "No tienes herramientas en esta vista: trabaja solo con el resumen de datos de abajo y avisa de que el detalle completo no está disponible.",
        "",
        "Resumen de datos:",
        digest(),
      ].join("\n");
    }

    function tools() {
      const wrap = (fn) => (input) => fn(input || {});
      return [
        { name: "get_status", description: "Regulación activa, ventana, mecánicas, timers, antigüedad de los datos y avisos. Devuelve un objeto pequeño.", execute: wrap(() => status()) },
        { name: "get_usage", description: "Ranking de uso. segment: in_person (por defecto), online o total; top: 1-40. Devuelve nombre, % de uso, win rate y conversión a día 2.",
          inputSchema: { type: "object", properties: { segment: { type: "string", enum: SEGMENTS }, top: { type: "integer" } } },
          execute: wrap((i) => usage(String(i.segment || "in_person"), i.top)) },
        { name: "get_pokemon", description: "Ficha de una especie (acepta 'Mega Charizard Y', 'Basculegion-F'...): uso por segmento, Megas, sets habituales, compañeros, mejores/peores emparejamientos y equipos de top cut.",
          inputSchema: { type: "object", properties: { name: { type: "string" } }, required: ["name"] },
          execute: wrap((i) => pokemon(String(i.name || ""))) },
        { name: "get_matchup", description: "Win rate de team sheet entre dos especies en torneos presenciales.",
          inputSchema: { type: "object", properties: { a: { type: "string" }, b: { type: "string" } }, required: ["a", "b"] },
          execute: wrap((i) => matchup(String(i.a || ""), String(i.b || ""))) },
        { name: "get_top_cut", description: "Equipos de top cut con sets. segment: in_person u online; species opcional para filtrar; limit 1-12.",
          inputSchema: { type: "object", properties: { segment: { type: "string", enum: ["in_person", "online"] }, species: { type: "string" }, limit: { type: "integer" } } },
          execute: wrap((i) => topCut(i.segment ? String(i.segment) : null, i.species ? String(i.species) : null, i.limit)) },
        { name: "analyze_team", description: "Analiza un equipo pegado por el usuario (formato Showdown o 'Nombre @ Objeto | Habilidad | Naturaleza | mov, mov'): uso y conversión de cada miembro, sets poco comunes, cores presentes en el meta, amenazas.",
          inputSchema: { type: "object", properties: { team: { type: "string" } }, required: ["team"] },
          execute: wrap((i) => analyzeTeam(String(i.team || ""))) },
        { name: "calc_damage", description: "Cálculo exacto de daño (nivel 50, mecánica Champions). stat_points: {hp,atk,def,spa,spd,spe} 0-32, total 66. Un Pokémon con su Megapiedra se calcula como Mega. weather: sun/rain/sand/snow.",
          inputSchema: { type: "object", properties: {
            attacker: { type: "object", properties: { species: { type: "string" }, item: { type: "string" }, ability: { type: "string" }, nature: { type: "string" }, stat_points: { type: "object" }, boosts: { type: "object" } }, required: ["species"] },
            defender: { type: "object", properties: { species: { type: "string" }, item: { type: "string" }, ability: { type: "string" }, nature: { type: "string" }, stat_points: { type: "object" }, boosts: { type: "object" } }, required: ["species"] },
            move: { type: "string" }, weather: { type: "string" }, terrain: { type: "string" }, format: { type: "string", enum: ["doubles", "singles"] }, crit: { type: "boolean" },
            attacker_side: { type: "object" }, defender_side: { type: "object" } }, required: ["attacker", "defender", "move"] },
          execute: wrap((i) => calcDamage(i)) },
        { name: "calc_speed", description: "Compara velocidades finales (naturaleza, stat points, boosts.spe, Choice Scarf, tailwind: true).",
          inputSchema: { type: "object", properties: {
            a: { type: "object", properties: { species: { type: "string" }, item: { type: "string" }, nature: { type: "string" }, stat_points: { type: "object" }, boosts: { type: "object" }, tailwind: { type: "boolean" } }, required: ["species"] },
            b: { type: "object", properties: { species: { type: "string" }, item: { type: "string" }, nature: { type: "string" }, stat_points: { type: "object" }, boosts: { type: "object" }, tailwind: { type: "boolean" } }, required: ["species"] } }, required: ["a", "b"] },
          execute: wrap((i) => calcSpeed(i)) },
      ];
    }

    return { status, usage, pokemon, matchup, topCut, parseTeam, analyzeTeam, resolveSpecies, megaFor, calcDamage, calcSpeed, digest, instructions, tools, usageRows, megas, display };
  }

  return { create, slug, pct };
});
