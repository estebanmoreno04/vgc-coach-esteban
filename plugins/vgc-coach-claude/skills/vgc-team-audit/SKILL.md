---
name: vgc-team-audit
description: Use when a Pokemon Champions team needs a findings-first audit.
---

<!-- Modified in the estebanmoreno04 fork: reads the active regulation and meta from data/current. -->

# VGC Team Audit

Perform a findings-first competitive audit of a team. Preserve the identity unless the identity itself is the problem.

## Inputs
- full team
- optional target concerns
- optional target matchups
- optional event or ladder context

If format is omitted, use the active regulation from `data/current/regulation.json` and say so.

## Output
Return these sections in order:

1. `Top Findings`
2. `Team Identity`
3. `Matchup Holes`
4. `Recommended Changes`
5. `Residual Risk`

## Section focus
- `Top Findings`: highest-impact structural problems first, with gameplay consequences
- `Team Identity`: what the team is trying to do, and whether that identity is sound or under-supported
- `Matchup Holes`: real pressure points, not generic type-chart recap
- `Recommended Changes`: smallest useful fixes first, each tied to the exact problem solved
- `Residual Risk`: what stays shaky after the proposed changes

## Workflow
0. Run `python3 tools/meta_query.py status`, then pass the team to `python3 tools/meta_query.py team` (Showdown export or `Name @ Item | Ability | Nature | moves` lines on stdin or `--file`). Use its per-slot usage, win rate and day 2 conversion, set comparison, cores, threats and favourable matchups as evidence; warn and offer `vgc-refresh` when the status reports `needs_refresh`.
1. Identify what the team is trying to do before criticizing it.
2. Separate structural flaws from stylistic differences.
3. Surface the highest-impact issues first.
4. Tie every issue to a concrete gameplay consequence or recurring loss pattern.
5. Recommend the smallest useful fixes before larger rebuilds.
6. Preserve the identity unless the identity itself creates the failure.
7. End with residual risk instead of pretending the team is solved.

## Required behavior
- Read [Current Data Contract](../../docs/skills/shared/references/current-data.md), [audit-checklist](../../docs/skills/vgc-team-audit/references/audit-checklist.md), [Verification Packet](../../docs/skills/shared/references/verification-packet.md), and [output-rubric](../../docs/skills/vgc-team-audit/references/output-rubric.md) before finalizing.
- `Top Findings` must open with the data basis: regulation id and label from `regulation.json`, snapshot date and age, and whether the meta is early. Never read `data/archive/`.
- Ground field assumptions in the snapshot, in-person data first (the most common in-person cores and top cut teams are the matchups that matter most); browse live only for events after the snapshot's `data_through`.
- Label team-sheet matchup numbers as directional: they count species on each team, not species brought.
- Consume or summarize verification-packet confidence when findings depend on current field assumptions, species legality, item legality, move access, mechanics, or exact matchup claims.
- Findings first, not a compliment sandwich.
- Keep fixes concrete, proportional, and identity-preserving when reasonable.
- Do not flatten unconventional teams into generic balance or recommend a major rebuild before proving a smaller fix is insufficient.
