---
name: vgc-lead-planner
description: Use when a Pokemon Champions team needs lead plans and preserve targets.
---

<!-- Modified in the estebanmoreno04 fork: reads the active regulation and meta from data/current. -->

# VGC Lead Planner

Turn a team into real opening plans instead of fake full-game scripts.

## Inputs
- full team
- optional target matchups or archetypes
- optional target preserve targets or concerns
- optional open team sheet assumptions

If format is omitted, use the active regulation from `data/current/regulation.json` and say so.

## Output
Return these sections in order:

1. `Team Identity and Default Lead`
2. `Matchup Plans`
3. `Preserve Targets`
4. `Turn-One Priorities`
5. `Common Traps`
6. `Open Questions`

## Workflow
0. Run `python3 tools/meta_query.py status` and `python3 tools/meta_query.py team` with the user's team; pick the matchups to plan from the most common in-person cores and top cut teams (`meta_query.py top-cut --segment in_person`) unless the user named others. Warn and offer `vgc-refresh` when the status reports `needs_refresh`.
1. Identify what the team is trying to preserve or establish before naming leads.
2. Recommend one default lead that fits the normal game plan.
3. Change leads only when the matchup meaningfully changes the opening incentives.
4. Tie each lead to a concrete first-turn goal: board stabilization, speed control, immediate pressure, or pivot positioning.
5. Name preserve targets explicitly so the plan is not just "bring strong mons."
6. Surface real uncertainty instead of inventing exact lines from thin matchup claims.

## Required behavior
- Read [Current Data Contract](../../docs/skills/shared/references/current-data.md), [planning-checklist](../../docs/skills/vgc-lead-planner/references/planning-checklist.md), [Verification Packet](../../docs/skills/shared/references/verification-packet.md), and [output-rubric](../../docs/skills/vgc-lead-planner/references/output-rubric.md) before finalizing.
- `Team Identity and Default Lead` must state the data basis: regulation id and label from `regulation.json`, snapshot date and age, and whether the meta is early. Never read `data/archive/`.
- Use the active regulation's timers and mechanics from `regulation.json` when they shape turn-one priorities.
- If the prep is opponent-specific and public info exists, use `vgc-opponent-scout` to tighten the matchup branches.
- If a turn-one plan hinges on one speed or survival benchmark, align that point with `vgc-calcs-assistant`.
- Ground current field assumptions in the snapshot; use live verification only for what happened after the snapshot's `data_through`.
- Consume or summarize verification-packet confidence when lead choices depend on current matchup assumptions, item legality, move access, speed, survival, or active mechanics.
- Avoid fake certainty, vague first-turn goals, or the same lead into every materially different matchup.
