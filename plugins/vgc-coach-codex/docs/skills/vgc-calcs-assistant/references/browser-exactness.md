# Exact Calc Paths

<!-- Modified in the estebanmoreno04 fork of NoahJenkins/vgc-coach: @smogon/calc is the primary backend; the browser path is the fallback. -->

## Primary path: `@smogon/calc`

Use the repo-local wrapper for fully specified damage, KO, survival and speed questions:

`python3 tools/damage_calc.py --request-file <json>` (or the JSON on stdin; on Windows use `python` or `py -3`)

- Backend `smogon-calc`: `@smogon/calc` (pinned in `tools/calc/package.json`) run through Node with Pokemon Champions mechanics: level 50, stat points (at most 32 per stat and 66 in total, sent in the `evs` fields), Champions damage modifiers and Mega forms.
- A Pokémon holding its Mega Stone is calculated as the Mega form, with the Mega form's ability; the wrapper says so in `assumptions_used.notes`.
- `calc_type` is `damage`, `ko`, `survival` or `speed`. Speed returns the final speed of both sides after nature, stat points, boosts, items, abilities and Tailwind, and which side is faster.
- Field options: `format` (`Doubles` or `Singles`), `weather`, `terrain`, and per-side flags `helping_hand`, `tailwind`, `reflect`, `light_screen`, `aurora_veil`, `friend_guard`; `is_crit` for critical hits; per-side `boosts`, `status` and `current_hp_percent`.
- Setup: Node.js plus `npm ci` in `tools/calc` (done once).

Example request:

```json
{
  "calc_type": "ko",
  "move": "Heat Wave",
  "attacker": {"species": "Charizard", "item": "Charizardite Y", "nature": "Modest", "evs": {"sa": 32}},
  "defender": {"species": "Kingambit", "nature": "Adamant", "evs": {"hp": 32}},
  "field": {"format": "Doubles", "weather": "Sun"}
}
```

## Fallback path: browser calc

When Node or the calc package is unavailable, damage, KO and survival requests fall back to the upstream browser path (`tools/browser_damage_calc.py`: `agent-browser` driving the Pikalytics calc, POSIX only). Speed has no browser fallback.

The calc path is a support tool, not the user-facing output. Final answers still need to stay decision-first.

## Exact Eligibility

Attempt an exact run only when all of these are true:

- attacker and defender species are known
- the move is known (except for speed)
- level, nature, item, ability, and spread assumptions are explicit enough to encode honestly
- the spread is legal for the active ruleset

If any of those fail, stay in benchmark-framing mode.

## Fallback Rules

If a run returns `fallback` or `blocked`:

- say exact verification did not complete
- keep the assumptions list explicit
- continue with the smallest honest benchmark answer that still helps the decision
- do not restate stale or guessed numbers as exact

## Scope Boundary

Exact support covers damage ranges, KO odds, survival thresholds and speed comparisons. It does not cover full-turn simulations, unrevealed opposing spreads (state them as assumptions), or field mechanics the wrapper cannot encode safely.

For `vgc-team-builder` handoffs:

- exact evidence can justify damage, KO, survival and speed benchmarks inside the final spread notes
- the calc response should stay narrow enough for the builder to synthesize into one final team output
