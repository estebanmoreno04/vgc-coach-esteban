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
      .normalize("NFKD").replace(/\p{M}/gu, "")
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
    const byEvent = (DATA.by_event || []).map((e) => ({
      key: e[0], name: e[1], date: e[2], players: e[3], basis: e[4], teams: e[5], day2_teams: e[6], url: e[7],
      usage: e[8].map((r) => ({ species: r[0], teams: r[1], share: r[2], win_rate: r[3], day2_conversion: r[4], top_cut_teams: r[5] })),
      megas: e[9].map((r) => ({ mega: r[0], teams: r[1], share: r[2], win_rate: r[3] })),
      segment: e[10], top: e[11] || [],
    }));
    const regionals = byEvent.filter((e) => e.segment === "in_person");
    const trendData = DATA.trend || { available: false, species: [], megas: [] };
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
        proven_day2_set: provenSet(species),
        partners_in_person: partners,
        best_matchups: records.slice(0, 5),
        worst_matchups: records.slice(-5).reverse(),
        matchup_basis: "team sheets (especies del equipo, no las que salieron a jugar)",
        top_cut_teams: teams.length,
        recent_top_cut: teams.slice(0, 3).map(formatTeam),
        by_event: regionals.map((e) => {
          const r = e.usage.find((u) => u.species === species);
          return { event: e.name, date: e.date, share_pct: r ? pct(r.share) : 0, win_rate_pct: r ? pct(r.win_rate) : null, top_cut_teams: r ? r.top_cut_teams : 0 };
        }),
      };
    }

    function shortEvent(name) {
      return String(name).replace(/\s+Regional Championships.*$/i, "").replace(/\s+Championships.*$/i, "").trim() || name;
    }

    function trend(top) {
      if (!trendData.available) return { available: false, reason: "Aún no hay suficientes regionales para comparar recientes y anteriores." };
      const n = Math.min(Math.max(Number(top) || 8, 1), 20);
      const rows = (list) => list.map((r) => ({
        id: r[0], name: display(r[0]), before_pct: pct(r[1]), recent_pct: pct(r[2]), recent_win_rate_pct: pct(r[3]), change_pts: Math.round(r[4] * 1000) / 10,
      }));
      const species = rows(trendData.species);
      const megaRows = rows(trendData.megas);
      return {
        available: true,
        recent_events: trendData.recent.map(([name, date]) => `${name} (${date})`),
        earlier_events: trendData.earlier.map(([name, date]) => `${name} (${date})`),
        recent_teams: trendData.recent_teams, earlier_teams: trendData.earlier_teams,
        basis: "regionales presenciales con el field completo; cambio en puntos de % de uso",
        risers: species.filter((r) => r.change_pts > 0).slice(0, n),
        fallers: species.filter((r) => r.change_pts < 0).reverse().slice(0, n),
        mega_risers: megaRows.filter((r) => r.change_pts > 0).slice(0, n),
        mega_fallers: megaRows.filter((r) => r.change_pts < 0).reverse().slice(0, n),
      };
    }

    // Usage of each species at the latest whole-field regionals, oldest first (for the trend chart).
    const usageAt = new Map(regionals.map((e) => [e.key, new Map(e.usage.map((u) => [u.species, u.share]))]));
    function regionalSeries(ids, count) {
      const events = regionals.filter((e) => e.basis === "full_field").slice(0, count || 5).reverse();
      return {
        events: events.map((e) => ({ key: e.key, name: shortEvent(e.name), date: e.date, teams: e.teams })),
        series: ids.map((id) => ({ id, name: display(id), values: events.map((e) => usageAt.get(e.key).get(id) || 0) })),
      };
    }

    function listEvents(segment) {
      return byEvent.filter((e) => !segment || e.segment === segment)
        .map((e) => ({ name: e.name, date: e.date, segment: e.segment, players: e.players, teams: e.teams, basis: e.basis }));
    }

    function formatTop(e) {
      return e.top.map(([placement, player, country, record, team]) => ({
        event: e.name, date: e.date, placement, player, country, record,
        team: team.map(([n, item, ab, nat, moves]) => `${n} @ ${item || "?"} | ${ab || "?"} | ${nat || "?"} | ${(moves || []).join(", ")}`),
      }));
    }

    function eventUsage(name, top) {
      const key = slug(name);
      const latest = /^(ultimo|el-ultimo|last|latest|reciente|mas-reciente|ultimo-regional)$/.test(key);
      const ordered = [...regionals, ...byEvent.filter((e) => e.segment !== "in_person")];
      const found = latest ? regionals[0] : ordered.find((e) => key && (slug(e.name).includes(key) || slug(e.key).includes(key)));
      if (!found) throw new Error(`No hay ningún torneo que coincida con "${name}". Regionales en los datos: ${regionals.map((e) => `${e.name} (${e.date})`).join(", ")}.`);
      const n = Math.min(Math.max(Number(top) || 15, 1), 40);
      return {
        name: found.name, date: found.date, segment: found.segment === "in_person" ? "presencial" : "online", players: found.players, teams: found.teams, day2_teams: found.day2_teams,
        basis: found.basis === "full_field" ? "field completo" : "solo equipos de día 2",
        usage: found.usage.slice(0, n).map((r) => ({ name: display(r.species), share_pct: pct(r.share), win_rate_pct: pct(r.win_rate), day2_conversion_pct: pct(r.day2_conversion), top_cut_teams: r.top_cut_teams })),
        megas: found.megas.slice(0, 10).map((r) => ({ name: display(r.mega), share_pct: pct(r.share), win_rate_pct: pct(r.win_rate) })),
        top_cut: formatTop(found),
      };
    }

    // Proven sets: what in-person teams that made day 2 actually ran.
    const MIN_DAY2_SAMPLE = 8;
    function provenSet(species) {
      const day2 = (DATA.sets[species] || {}).day2;
      if (!day2 || !day2.sample) return null;
      return {
        day2_teams: day2.sample,
        small_sample: day2.sample < MIN_DAY2_SAMPLE,
        moves: day2.moves.map(([n, s]) => `${n} ${pct(s)}%`),
        items: day2.items.slice(0, 4).map(([n, s]) => `${n} ${pct(s)}%`),
        abilities: day2.abilities.map(([n, s]) => `${n} ${pct(s)}%`),
        natures: day2.natures.slice(0, 3).map(([n, s]) => `${n} ${pct(s)}%`),
        common_set: day2.top_sets[0] ? `${day2.top_sets[0][0]} | ${day2.top_sets[0][1]} | ${day2.top_sets[0][2]} | ${day2.top_sets[0][3].join(", ")}` : null,
      };
    }
    function provenMove(species, move) {
      const day2 = (DATA.sets[species] || {}).day2;
      if (!day2 || day2.sample < MIN_DAY2_SAMPLE) return null;
      return day2.moves.some(([n]) => slug(n) === slug(move));
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

    // -- type mechanics ------------------------------------------------------------
    // Team-sheet win rates are correlations between whole teams; these checks say what
    // actually hits what, using the moves each side really runs (proven day 2 sets for opponents).
    const IMMUNE_BY_ABILITY = {
      levitate: "Ground", eartheater: "Ground", flashfire: "Fire", wellbakedbody: "Fire",
      waterabsorb: "Water", stormdrain: "Water", dryskin: "Water", voltabsorb: "Electric",
      lightningrod: "Electric", motordrive: "Electric", sapsipper: "Grass",
    };
    const WEATHER_BALL = { drought: "Fire", drizzle: "Water", sandstream: "Rock", snowwarning: "Ice" };
    const calcId = (name) => slug(name).replace(/-/g, "");
    function formTypes(id) {
      if (!calcLib) return null;
      const gen = calcLib.Generations.get(0);
      const found = gen.species.get(calcId(display(id))) || gen.species.get(calcId(id));
      return found ? found.types.slice() : null;
    }
    function moveData(name, ability) {
      const gen = calcLib.Generations.get(0);
      const move = gen.moves.get(calcId(name));
      // Some status moves (Coil, Tailwind...) have no category in the calc data: only Physical/Special hit.
      if (!move || (move.category !== "Physical" && move.category !== "Special")) return null;
      const type = calcId(name) === "weatherball" && WEATHER_BALL[calcId(ability || "")] ? WEATHER_BALL[calcId(ability)] : move.type;
      return { name: move.name, type };
    }
    function effectiveness(type, defTypes, defAbility) {
      if (IMMUNE_BY_ABILITY[calcId(defAbility || "")] === type) return 0;
      const chart = calcLib.Generations.get(0).types.get(calcId(type));
      return defTypes.reduce((x, t) => x * (chart && chart.effectiveness[t] !== undefined ? chart.effectiveness[t] : 1), 1);
    }
    // Opponent as it is really played: its most common day 2 set (Mega form included).
    function provenSide(species) {
      const day2 = (DATA.sets[species] || {}).day2;
      const set = day2 && day2.top_sets[0];
      const mega = set ? megaFor(species, set[0]) : null;
      const moves = day2 && day2.sample ? day2.moves.filter(([, share]) => share >= 0.15).map(([n]) => n) : [];
      return { id: mega || species, name: display(mega || species), ability: set ? set[1] : null, moves };
    }
    function bestHit(attacker, defender) {
      const defTypes = formTypes(defender.id);
      if (!defTypes) return null;
      let best = null;
      for (const name of attacker.moves) {
        const move = moveData(name, attacker.ability);
        if (!move) continue;
        const x = effectiveness(move.type, defTypes, defender.ability);
        if (!best || x > best.x) best = { move: move.name, type: move.type, x };
      }
      return best;
    }
    const times = (x) => (x === 0 ? "inmune" : `×${x}`);
    function mechanics(opponentSpecies, roster) {
      if (!calcLib) return null;
      const opp = provenSide(opponentSpecies);
      if (!opp.moves.length) return { note: "Sin set de día 2 suficiente para comprobar tipos." };
      const threatens = [], answered_by = [], walled = [], bad_for = [];
      for (const mon of roster) {
        const theirs = bestHit(opp, mon);
        const ours = bestHit(mon, opp);
        if (theirs && theirs.x >= 2) threatens.push(`${theirs.move} (${theirs.type}) ${times(theirs.x)} → ${mon.name}`);
        if (ours && ours.x >= 2) answered_by.push(`${mon.name}: ${ours.move} (${ours.type}) ${times(ours.x)}`);
        if (ours && ours.x <= 0.5) walled.push(`${mon.name}: su mejor golpe es ${ours.move} ${times(ours.x)}`);
        if (theirs && ours && theirs.x >= 2 && ours.x <= 0.5) bad_for.push(`${mon.name}: recibe ${theirs.move} ${times(theirs.x)} y su mejor golpe es ${ours.move} ${times(ours.x)}`);
      }
      return { opponent_form: opp.name, opponent_moves_checked: opp.moves, threatens, answered_by, walled, bad_for };
    }
    function typeMatchup(a, b) {
      if (!calcLib) throw new Error("La calculadora no ha cargado en esta página.");
      const side = (name) => { const r = resolveSpecies(name); return r.mega ? { ...provenSide(r.species), id: r.mega, name: display(r.mega) } : provenSide(r.species); };
      const x = side(a), y = side(b);
      const hits = (att, def) => att.moves.map((n) => moveData(n, att.ability)).filter(Boolean)
        .map((m) => ({ move: m.name, type: m.type, effectiveness: effectiveness(m.type, formTypes(def.id) || [], def.ability) }))
        .sort((p, q) => q.effectiveness - p.effectiveness);
      return {
        a: { form: x.name, types: formTypes(x.id), ability: x.ability, moves: x.moves },
        b: { form: y.name, types: formTypes(y.id), ability: y.ability, moves: y.moves },
        a_hits_b: hits(x, y), b_hits_a: hits(y, x),
        basis: "tipos de los movimientos de sus sets de día 2 más comunes (y habilidades que dan inmunidad); no incluye daño exacto: usa calc_damage para eso",
      };
    }

    function analyzeTeam(text) {
      const parsed = parseTeam(text);
      if (!parsed.length) throw new Error("No he podido leer ningún Pokémon del equipo.");
      const members = [];
      const fighters = [];
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
        const mega = megaFor(species, mon.item);
        fighters.push({ id: mega || species, name: display(mega || species), ability: mon.ability || (provenSide(species).ability), moves: mon.moves });
        members.push({
          name: display(species), mega: display(mega),
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
      const threats = [...tally.entries()].map(([s, [w, g]]) => ({ name: display(s), species: s, win_rate_vs_team_pct: pct(w / g), games: g }))
        .sort((x, y) => y.win_rate_vs_team_pct - x.win_rate_vs_team_pct);
      const withSet = (list, favourable) => list.map(({ species, ...rest }) => {
        const proven = provenSet(species);
        const mech = mechanics(species, fighters);
        const row = { ...rest, proven_day2_set: proven ? proven.common_set : null, proven_day2_moves: proven ? proven.moves.slice(0, 6) : [], type_check: mech };
        if (favourable && mech && mech.threatens && mech.threatens.length > mech.answered_by.length) {
          row.warning = "El win rate de team sheet sale favorable, pero por tipos te amenaza más de lo que tú le amenazas: no lo presentes como favorable.";
        } else if (favourable && mech && mech.bad_for && mech.bad_for.length) {
          row.warning = `Favorable para el equipo en conjunto, pero muy malo para ${mech.bad_for.map((b) => b.split(":")[0]).join(" y ")} (ver bad_for): no lo uses como motivo para llevar ese Pokémon.`;
        }
        return row;
      });
      members.forEach((m) => delete m.species);
      return {
        members, cores_in_person: cores, biggest_threats: withSet(threats.slice(0, 6), false), most_favourable: withSet(threats.slice(-4).reverse(), true),
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
      const attackerSpecies = (() => { try { return resolveSpecies(input.attacker.species).species; } catch (e) { return null; } })();
      if (attackerSpecies && provenMove(attackerSpecies, move.name) === false) {
        const proven = provenSet(attackerSpecies);
        notes.push(`${display(attackerSpecies)} no ha llevado ${move.name} en ningún equipo de día 2 (${proven.day2_teams} equipos). Movimientos contrastados: ${proven.moves.slice(0, 6).join(", ")}.`);
      }
      const result = calcLib.calculate(gen, attacker, defender, move, field);
      const [min, max] = result.range();
      const hp = defender.maxHP();
      let ko = "";
      try { ko = result.kochance().text; } catch (e) { ko = ""; }
      return {
        summary: max === 0 ? `${attacker.name} ${move.name} contra ${defender.name}: no hace daño (inmune o sin efecto)` : (() => { try { return result.desc(); } catch (e) { return `${attacker.name} ${move.name} contra ${defender.name}`; } })(),
        damage: [min, max], percent: [Math.round(1000 * min / hp) / 10, Math.round(1000 * max / hp) / 10],
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
      const t = trend(5);
      const moves = (list) => list.map((r) => `${r.name} ${r.before_pct}% → ${r.recent_pct}%`).join(", ");
      return [
        `Regulación activa: ${s.label || s.regulation} (${s.regulation}), ventana ${s.window ? s.window.start : "?"} → ${s.window && s.window.end ? s.window.end : "?"}.`,
        `Mecánicas: ${(s.mechanics || []).join(", ") || "ninguna especial"}. Objetos duplicados permitidos: ${s.rules && s.rules.held_items ? s.rules.held_items.duplicates_allowed : "?"}.`,
        `Datos generados ${s.snapshot_generated_at} (hace ${s.snapshot_age_days} días), con torneos hasta ${s.data_through}. Meta temprano: ${s.early_meta ? "sí" : "no"}.`,
        `Presencial: ${s.segments.in_person.events} eventos, ${s.segments.in_person.teams} equipos (field completo), ${s.segments.in_person.day2_teams} de día 2. Online: ${s.segments.online.events} torneos, ${s.segments.online.teams} equipos.`,
        s.alerts.length ? "Avisos: " + s.alerts.join(" ") : "",
        "Regionales incluidos (del más reciente al más antiguo): " + regionals.map((e) => `${shortEvent(e.name)} ${e.date} (${e.players} jugadores)`).join(", ") + ".",
        "Top uso presencial (todos los regionales juntos):\n" + top,
        "Megas más usadas (presencial, todos los regionales): " + megaTop,
        t.available
          ? `Tendencia (${t.recent_events.join(", ")} frente a los anteriores): suben ${moves(t.risers)}; bajan ${moves(t.fallers)}.`
          : "",
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
        "- Las cifras agregadas mezclan todos los regionales de la regulación. Para preguntas sobre cómo ha cambiado el meta, o para preparar un torneo próximo, da más peso a los regionales recientes: usa la tendencia y los datos por regional, y di qué regionales cubre cada cifra.",
        "- Los emparejamientos son a nivel de team sheet (orientativos). Los stat points de los rivales no se publican: en cálculos, decláralos como supuesto.",
        "- Respeta las mecánicas de la regulación: si Terastal no está en la lista, no hables de Tera.",
        "- Si algo no está en los datos (otra regulación, un torneo posterior a la fecha de los datos), dilo claramente.",
        "- Los win rates de emparejamiento (team sheet) son correlaciones entre equipos enteros, no causas. Nunca digas que un rival es favorable, o una amenaza, solo por ese número: contrástalo con la mecánica (type_check de analyze_team, get_type_matchup, velocidades y calc_damage). Si el número y la mecánica se contradicen, dilo así y da prioridad a la mecánica; por ejemplo, un Pokémon que te golpea súper eficaz y resiste tus golpes no es favorable aunque su win rate contra tu team sheet sea bajo.",
        "- Al comparar dos versiones de un equipo, explica qué cambia en partida por el Pokémon que entra y el que sale: contra qué rivales del meta gana o pierde ese miembro por tipos, velocidad y cálculos (bad_for y walled de type_check, get_type_matchup). Un rival que mejora la estadística del equipo pero que es malo para el miembro nuevo no es un motivo para elegirlo.",
        "- Usa solo sets contrastados: movimientos, objetos, habilidades y naturalezas que aparecen en equipos presenciales de día 2 (proven_day2_set en get_pokemon y en las amenazas de analyze_team). Para amenazas, enfrentamientos y cálculos contra rivales, usa su set de día 2 más común. No menciones movimientos que nunca han llegado a día 2 salvo que el usuario pregunte por ellos; si calc_damage avisa de que un movimiento no es contrastado, cámbialo por uno que sí lo sea. Si la muestra de día 2 es pequeña (small_sample), dilo.",
        "- Para auditar un equipo: identidad, 2-4 hallazgos ordenados por impacto con su consecuencia en partida, cambios mínimos primero, riesgo residual.",
        "- Si te preguntan algo que no es de Pokémon VGC, responde en una frase que solo ayudas con VGC.",
        withTools
          ? "Tienes herramientas para consultar los datos (uso, tendencia, cada regional, Pokémon, emparejamientos, top cut, análisis de equipo, daño y velocidad). Úsalas en lugar de suponer."
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
        { name: "get_trend", description: "Cómo se mueve el meta presencial: los últimos regionales frente a los anteriores. Devuelve qué Pokémon y Megas suben y bajan (uso antes, uso reciente, cambio en puntos, win rate reciente). top: 1-20.",
          inputSchema: { type: "object", properties: { top: { type: "integer" } } },
          execute: wrap((i) => trend(i.top)) },
        { name: "get_event", description: "Uso, Megas y mejores equipos de UN torneo concreto: un regional presencial (ciudad o nombre, p. ej. 'Nice'; 'ultimo' para el regional más reciente) o un torneo online (parte de su nombre). top: 1-40. Si no existe, devuelve la lista de regionales.",
          inputSchema: { type: "object", properties: { name: { type: "string" }, top: { type: "integer" } }, required: ["name"] },
          execute: wrap((i) => eventUsage(String(i.name || ""), i.top)) },
        { name: "get_pokemon", description: "Ficha de una especie (acepta 'Mega Charizard Y', 'Basculegion-F'...): uso por segmento, uso en cada regional (by_event), Megas, sets habituales, compañeros, mejores/peores emparejamientos y equipos de top cut.",
          inputSchema: { type: "object", properties: { name: { type: "string" } }, required: ["name"] },
          execute: wrap((i) => pokemon(String(i.name || ""))) },
        { name: "get_matchup", description: "Win rate de team sheet entre dos especies en torneos presenciales.",
          inputSchema: { type: "object", properties: { a: { type: "string" }, b: { type: "string" } }, required: ["a", "b"] },
          execute: wrap((i) => matchup(String(i.a || ""), String(i.b || ""))) },
        { name: "get_type_matchup", description: "Comprueba por tipos qué se hacen dos Pokémon con sus sets de día 2 más comunes (forma Mega incluida; acepta 'Mega Floette'): efectividad de cada movimiento en ambas direcciones e inmunidades por habilidad. Úsalo antes de llamar favorable o amenaza a un rival.",
          inputSchema: { type: "object", properties: { a: { type: "string" }, b: { type: "string" } }, required: ["a", "b"] },
          execute: wrap((i) => typeMatchup(String(i.a || ""), String(i.b || ""))) },
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

    return { status, usage, pokemon, matchup, topCut, trend, regionalSeries, listEvents, eventUsage, shortEvent, parseTeam, analyzeTeam, resolveSpecies, megaFor, calcDamage, calcSpeed, typeMatchup, digest, instructions, tools, usageRows, megas, byEvent, regionals, display };
  }

  return { create, slug, pct };
});
