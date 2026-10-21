# Fork Changes

This repository is a fork of [NoahJenkins/vgc-coach](https://github.com/NoahJenkins/vgc-coach), licensed under [Apache-2.0](./LICENSE). As required by section 4(b) of the license, this file lists the files modified in the fork. Each modified file also carries a short modification notice where its format allows comments.

## Modified files

| File | Change |
|---|---|
| `README.md` | Fork notice and data credits. |
| `.gitignore` | Ignores the pipeline HTTP cache (`data/cache/`). |
| `.github/workflows/plugin-package-ci.yml` | Installs `tools/requirements-data.txt` for the resolver tests. |

## Added files

| File | Purpose |
|---|---|
| `config/vgc-data.yaml` | Source and pipeline configuration (no regulation ids). |
| `tools/resolve_regulation.py` | CLI that detects the active regulation. |
| `tools/vgc_data/` | Polite HTTP client, source adapters and resolver logic. |
| `tools/requirements-data.txt` | Pinned data pipeline dependencies. |
| `data/schemas/regulation-v1.schema.json` | Schema of `data/current/regulation.json`. |
| `data/current/regulation.json` | Active regulation written by the resolver. |
| `tests/test_resolve_regulation.py`, `tests/fixtures/regulation/` | Resolver tests and fixtures. |
| `FORK_CHANGES.md` | This file. |

Generated plugin packages under `plugins/` are rebuilt with `python3 tools/build_plugins.py build` and are not edited by hand.
