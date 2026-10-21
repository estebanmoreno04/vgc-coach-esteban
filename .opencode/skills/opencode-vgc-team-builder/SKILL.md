---
name: opencode-vgc-team-builder
description: Use when building one practical Pokemon Champions team around a target idea in OpenCode.
compatibility: opencode
---

OpenCode wrapper for the shared `vgc-team-builder` contract.

Read and follow these shared repo files directly:
- `skills/vgc-team-builder/SKILL.md`
- `docs/skills/vgc-team-builder/references/build-principles.md`
- `docs/skills/vgc-team-builder/references/output-rubric.md`
- `docs/skills/shared/references/current-data.md` (active regulation and meta come from `data/current/`; never from `data/archive/`)

<!-- Modified in the estebanmoreno04 fork: legality comes from data/current instead of a hand-written regulation note. -->

Treat `data/current/regulation.json` and `data/current/snapshot.json` as hard constraints for current builds:
- only give `Terastallization` recommendations if `terastallization` is listed in the regulation's `mechanics`
- only one Mega Stone user belongs on the team when Mega Evolution is active
- if an item is not seen on current official team sheets or in the official announcement, do not name a speculative item; mark the item direction as unverified instead
- prefer species evidenced in the current snapshot over older-format carryovers when uncertainty is high

When the shared contract says to use another repo skill, load the matching `opencode-vgc-*` wrapper instead of a shared `vgc-*` skill name.

Use repo files directly. Do not read from `.claude/skills/...` or `.agents/skills/...`.
