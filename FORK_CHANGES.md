# Fork Changes

This repository is a fork of [NoahJenkins/vgc-coach](https://github.com/NoahJenkins/vgc-coach), licensed under [Apache-2.0](./LICENSE). As required by section 4(b) of the license, this file lists the files modified in the fork. Each modified file also carries a short modification notice where its format allows comments.

## Modified files

| File | Change |
|---|---|
| `README.md` | Fork notice, data credits, `data/current` and `data/archive` paths. |
| `.gitignore` | Ignores the pipeline HTTP cache (`data/cache/`). |
| `.github/workflows/plugin-package-ci.yml` | Installs `tools/requirements-data.txt` for the resolver tests. |
| `skills/vgc-meta-research`, `vgc-team-builder`, `vgc-team-audit`, `vgc-lead-planner`, `vgc-opponent-scout`, `vgc-format-verifier` (`SKILL.md`) | Read the active regulation and meta from `data/current/` via `tools/meta_query.py`, state the data basis, warn on stale or early data, browse live only after the snapshot, never use `data/archive/`. |
| `.opencode/skills/*/SKILL.md` | Point to the current-data contract instead of a hand-written legality note. |
| `docs/skills/shared/references/live-source-registry.yaml`, `live-source-map.md` | No pinned regulation; approved live-check sources. |
| `docs/skills/shared/references/verification-packet.md`, `battle-state-v1.md` | `data/current` replaces hand-written snapshots. |
| `docs/skills/*/examples/*.md`, `docs/evals/*.md` | No regulation ids in examples and checklists. |
| `docs/runtime/claude-code.md` | Current-data and Windows notes. |
| `tools/check_format_freshness.py`, `tools/render_source_registry_docs.py`, `tools/generate_site_trust_data.py`, `tools/build_plugins.py`, `tools/plugin_manifest.json` | Validate and package `data/current` instead of hand-written regulation artifacts; package the query tool and the new skill. |
| `tests/test_format_freshness.py`, `tests/test_source_registry.py`, `tests/test_generate_site_trust_data.py` | Updated for the auto-detected regulation. |
| `site/src/generated/trustData.ts`, `RELEASE_NOTES.md` | Regenerated. |

## Removed or moved files

| File | Change |
|---|---|
| `docs/skills/shared/references/champions-reg-*-legality.md` | Removed: hand-written regulation notes. |
| `data/snapshots/*` | Moved to `data/archive/upstream-snapshots/` as history. |

## Added files

| File | Purpose |
|---|---|
| `config/vgc-data.yaml` | Source and pipeline configuration (no regulation ids). |
| `tools/resolve_regulation.py` | CLI that detects the active regulation. |
| `tools/build_snapshot.py` | CLI that downloads the active regulation's tournaments and builds the meta snapshot. |
| `tools/vgc_data/` | Polite HTTP client, source adapters, resolver, event store, normalization and aggregation. |
| `tools/requirements-data.txt` | Pinned data pipeline dependencies. |
| `data/schemas/regulation-v1.schema.json` | Schema of `data/current/regulation.json`. |
| `data/schemas/meta-snapshot-v2.schema.json` | Schema of `data/current/snapshot.json`. |
| `data/current/` | Active regulation, snapshot, processed-event index, normalized events and species registry. |
| `tests/test_resolve_regulation.py`, `tests/test_build_snapshot.py`, `tests/test_meta_query.py`, `tests/fixtures/regulation/`, `tests/fixtures/snapshot/` | Pipeline, query and refresh tests and fixtures. |
| `tools/meta_query.py`, `tools/vgc_data/query.py` | Read-only queries over `data/current` (reused by skills, refresh and future front ends). |
| `tools/vgc_refresh.py`, `skills/vgc-refresh/`, `.claude/skills/vgc-refresh`, `.agents/skills/vgc-refresh`, `.opencode/skills/opencode-vgc-refresh/`, `.opencode/commands/vgc-refresh.md` | Refresh command and skill. |
| `docs/skills/shared/references/current-data.md` | How skills read the current regulation and meta. |
| `data/archive/upstream-snapshots/README.md` | Explains the archived upstream snapshots. |
| `FORK_CHANGES.md` | This file. |

Generated plugin packages under `plugins/` are rebuilt with `python3 tools/build_plugins.py build` and are not edited by hand.
