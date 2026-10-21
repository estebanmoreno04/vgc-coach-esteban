---
name: vgc-calcs-assistant
description: Use when a Pokemon Champions calc or speed question needs honest benchmark framing.
---

<!-- Modified in the estebanmoreno04 fork: @smogon/calc (Champions mechanics) is the primary exact backend, with exact speed. -->

# VGC Calcs Assistant

Convert calc questions into prep decisions, not fake precision.

## Inputs
- damage or KO questions
- survival benchmarks
- speed checks
- spread-tradeoff questions
- match-prep requests that hinge on one or two benchmark interactions
- builder handoff requests that already locked a team shell and need spread decisions

## Output
Return these sections in order:

1. `Calc Goal`
2. `Known Inputs`
3. `Relevant Benchmarks`
4. `Decision Impact`
5. `Missing Inputs or Confidence Limits`

## Workflow
1. Define the real decision before discussing numbers.
2. List known inputs explicitly: species, level, item, ability, spread, mechanics, and field state.
3. If the request is a fully specified damage, KO, survival or speed question, run `python3 tools/damage_calc.py` (on Windows `python` or `py -3`) with a structured JSON payload; it uses `@smogon/calc` with Pokemon Champions mechanics and falls back to the Pikalytics browser path for damage when Node is unavailable.
4. If critical exact inputs are missing, illegal for the active ruleset, or the calc returns `fallback` or `blocked`, switch to honest benchmark framing instead of inventing precision.
5. For speed questions, use `calc_type: "speed"`: it returns final speeds after nature, stat points, boosts, items, abilities and Tailwind. When common spreads are unknown, show the realistic band (for example neutral 0 points to positive nature 32 points) instead of one number.
6. For team-builder handoffs, answer the narrow benchmark question only and return the spread consequence cleanly for the builder to synthesize.
7. Prioritize the few benchmarks that change lead, set, EV, nature, or preserve decisions.
8. Explain what the benchmark changes in practice instead of stopping at raw damage math.
9. If a rules question blocks the calc, align with `vgc-format-verifier`.

## Required behavior
- Read [calc-checklist](../../docs/skills/vgc-calcs-assistant/references/calc-checklist.md), [browser-exactness](../../docs/skills/vgc-calcs-assistant/references/browser-exactness.md), and [output-rubric](../../docs/skills/vgc-calcs-assistant/references/output-rubric.md) before finalizing.
- If the request came from `vgc-team-builder`, also read [team-builder calcs handoff](../../docs/skills/shared/references/team-builder-calcs-handoff.md) before finalizing.
- Keep every exact claim tied to explicit assumptions.
- For fully specified damage, survival and speed requests, prefer `python3 tools/damage_calc.py` with a structured JSON payload over ad-hoc browser clicking; state which backend ran (`smogon-calc` or the browser fallback).
- Use exact numbers only when the run returned `status=exact`.
- If the exact run returned `fallback` or `blocked`, say exact verification did not complete and continue with benchmark framing.
- Use benchmark bands when the data is incomplete; common items, natures and abilities for the opposing species can come from `python3 tools/meta_query.py pokemon <name>` (stat points are not published on team sheets, so treat them as assumptions).
- Respect the active regulation's mechanics from `data/current/regulation.json` (no Tera unless listed; Mega forms only from their Mega Stone).
- For team-builder handoffs, return the benchmark goal, the locked assumptions, whether exact verification ran, and the spread consequence.
- For team-builder handoffs, do not turn the response into a full team export or a broad matchup essay.
- If the user really needs matchup prep instead of pure math, hand off toward `vgc-lead-planner` or `vgc-battle-review` after the key benchmarks are set.
- Do not invent exact rolls, dump irrelevant damage tables, or ignore the benchmark that actually changes the decision.
