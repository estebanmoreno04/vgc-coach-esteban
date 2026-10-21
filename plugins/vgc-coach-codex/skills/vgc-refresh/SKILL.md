---
name: vgc-refresh
description: Use when the user wants fresh Pokemon Champions data, or a skill reports the meta snapshot is stale or early.
---

<!-- Added in the estebanmoreno04 fork of NoahJenkins/vgc-coach. -->

# VGC Refresh

Update the coaching data for the active regulation and report what changed.

## Inputs
- an explicit refresh request ("update the meta", "refresh after this weekend's regionals")
- or a hand-off from another skill whose `meta_query.py status` reported `needs_refresh`

## What it runs

From the repository root (on Windows use `python` or `py -3` instead of `python3`):

```bash
python3 tools/vgc_refresh.py
```

This runs, in order:

1. `tools/resolve_regulation.py`: detects the active regulation from the official in-game news and community sources. If it changed, the previous data is archived to `data/archive/<previous id>/` and never used again.
2. `tools/build_snapshot.py`: downloads only tournaments not processed yet (in-person official events first, online events of 64+ players as a complement) and rebuilds `data/current/snapshot.json`.
3. `tools/build_plugins.py build`: refreshes the packaged plugins with the new data.

It needs network access and can take a few minutes on the first run of a regulation (the Limitless API is rate limited). `--offline` re-aggregates stored events without downloading; `--json` prints machine-readable output.

## Output
Return these sections in order:

1. `Regulation` - active regulation id and label, window, confidence; say clearly if it changed, and mention any announced next regulation with its start date
2. `New Data` - new events since the last refresh (date, name, in-person or online, players) and the snapshot totals
3. `Meta Movers` - in-person risers and fallers first, then online, as reported by the tool
4. `New Top Cut Teams` - new in-person top cut teams, briefly
5. `Warnings` - stale or low-confidence regulation, early meta, unavailable sources, pending online events

## Required behavior
- Read [Current Data Contract](../../docs/skills/shared/references/current-data.md) before finalizing.
- Run the tool rather than describing what it would do; report only what its output says. Do not invent movers, events or numbers.
- If the tool fails or a source errors, say which one and what data is missing; keep the previous snapshot as the basis and label it with its age.
- When this skill was triggered by another skill's stale-data warning, return to that request afterwards using the refreshed data.
- The refresh changes files under `data/current/` and `plugins/`; mention that they can be committed if the user keeps the repository under version control.
