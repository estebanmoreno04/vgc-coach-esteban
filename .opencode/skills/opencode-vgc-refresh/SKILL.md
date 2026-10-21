---
name: opencode-vgc-refresh
description: Use when the user wants fresh Pokemon Champions data in OpenCode, or a skill reports the meta snapshot is stale or early.
compatibility: opencode
---

<!-- Added in the estebanmoreno04 fork of NoahJenkins/vgc-coach. -->

OpenCode wrapper for the shared `vgc-refresh` contract.

Read and follow these shared repo files directly:
- `skills/vgc-refresh/SKILL.md`
- `docs/skills/shared/references/current-data.md`

When the shared contract says to use another repo skill, load the matching `opencode-vgc-*` wrapper instead of a shared `vgc-*` skill name.

Use repo files directly. Do not read from `.claude/skills/...` or `.agents/skills/...`.
