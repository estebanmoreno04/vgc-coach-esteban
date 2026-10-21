#!/usr/bin/env python3
"""Check that the coaching data in data/current is consistent and not expired.

Modified by estebanmoreno04 (fork of NoahJenkins/vgc-coach): the upstream
version checked hand-written regulation dates in the source registry, dated
snapshots and legality notes. The fork detects the regulation automatically,
so this check now validates data/current instead:

* data/current/regulation.json exists and matches its schema;
* its active window has not ended more than ``grace_days`` ago (the weekly
  refresh should have replaced it by then);
* data/current/snapshot.json, when present, is for the same regulation;
* no skill, wrapper or shared reference routes coaching to a hand-written
  regulation note or to data/archive/.

Snapshot age and early-meta status are reported as warnings, not failures.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path("config/vgc-data.yaml")
CURRENT_DIR = Path("data/current")
SCHEMA_PATH = Path("data/schemas/regulation-v1.schema.json")
DEFAULT_GRACE_DAYS = 8
SNAPSHOT_WARN_DAYS = 7
PROMPT_ROOTS = (
    Path("skills"),
    Path(".opencode/skills"),
    Path(".opencode/commands"),
    Path("docs/skills"),
)
_HAND_WRITTEN_NOTE = re.compile(r"champions-reg-[a-z0-9-]+-legality\.md")
_ARCHIVE_ROUTE = re.compile(r"(?:read|use|open|load)[^.\n]{0,40}data/archive/", re.IGNORECASE)


def _parse_utc(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be an ISO-8601 UTC timestamp ending in Z")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError(f"{label} must be a valid ISO-8601 UTC timestamp") from exc


def _grace_days(repo_root: Path) -> int:
    path = repo_root / CONFIG_PATH
    if not path.exists():
        return DEFAULT_GRACE_DAYS
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return int((config.get("resolver") or {}).get("window_grace_days", DEFAULT_GRACE_DAYS))


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: must be a JSON object")
    return payload


def _validate_schema(payload: dict[str, Any], schema_path: Path) -> None:
    if not schema_path.exists():
        return
    import jsonschema

    try:
        jsonschema.validate(payload, json.loads(schema_path.read_text(encoding="utf-8")))
    except jsonschema.ValidationError as exc:
        raise ValueError(f"data/current/regulation.json does not match its schema: {exc.message}") from exc


def find_issues(
    repo_root: Path = REPO_ROOT,
    *,
    now: datetime | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return (errors, warnings)."""
    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    checked_at = checked_at.astimezone(timezone.utc)

    errors: list[str] = []
    warnings: list[str] = []
    current = repo_root / CURRENT_DIR
    regulation_path = current / "regulation.json"
    if not regulation_path.exists():
        errors.append("data/current/regulation.json is missing; run tools/resolve_regulation.py")
        return tuple(errors), tuple(warnings)

    regulation = _load_json(regulation_path)
    _validate_schema(regulation, repo_root / SCHEMA_PATH)
    regulation_id = regulation["regulation_id"]
    window = regulation.get("active_window") or {}
    if window.get("end"):
        end = _parse_utc(window["end"], label="regulation.json active_window.end")
        grace = timedelta(days=_grace_days(repo_root))
        if checked_at > end + grace:
            errors.append(
                f"data/current/regulation.json still names {regulation_id}, whose window ended "
                f"{window['end']}; run tools/vgc_refresh.py"
            )
        elif checked_at > end:
            warnings.append(f"The window of {regulation_id} ended {window['end']}; a refresh is due.")
    if regulation.get("stale"):
        warnings.append("regulation.json is marked stale: no source could be read on the last check.")
    if regulation.get("confidence") == "low":
        warnings.append("regulation.json was resolved with low confidence.")

    snapshot_path = current / "snapshot.json"
    if snapshot_path.exists():
        snapshot = _load_json(snapshot_path)
        snapshot_regulation = (snapshot.get("regulation") or {}).get("regulation_id")
        if snapshot_regulation != regulation_id:
            errors.append(
                f"data/current/snapshot.json is for {snapshot_regulation} but the active regulation is "
                f"{regulation_id}; run tools/build_snapshot.py"
            )
        generated = _parse_utc(snapshot.get("generated_at"), label="snapshot.json generated_at")
        if checked_at - generated > timedelta(days=SNAPSHOT_WARN_DAYS):
            warnings.append(
                f"data/current/snapshot.json is {(checked_at - generated).days} days old; run tools/vgc_refresh.py"
            )
        if snapshot.get("early_meta"):
            warnings.append("The current snapshot is flagged early_meta.")
    else:
        warnings.append("data/current/snapshot.json is missing; run tools/build_snapshot.py")

    errors.extend(_prompt_routing_issues(repo_root))
    return tuple(errors), tuple(warnings)


def _prompt_routing_issues(repo_root: Path) -> list[str]:
    issues = []
    for root in PROMPT_ROOTS:
        base = repo_root / root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.md")):
            text = path.read_text(encoding="utf-8")
            relative = path.relative_to(repo_root).as_posix()
            for note in sorted(set(_HAND_WRITTEN_NOTE.findall(text))):
                issues.append(f"{relative} routes coaching to a hand-written regulation note ({note})")
            if path.name.startswith("failure-example"):
                continue  # failure examples describe what must not be done
            for line in text.splitlines():
                if _ARCHIVE_ROUTE.search(line) and not re.search(r"\b(never|not|only when)\b", line, re.IGNORECASE):
                    issues.append(f"{relative} routes coaching to data/archive/: {line.strip()}")
    return issues


def find_expired_current_artifacts(
    repo_root: Path = REPO_ROOT,
    *,
    now: datetime | None = None,
) -> tuple[str, ...]:
    """Upstream-compatible entry point: the blocking issues only."""
    return find_issues(repo_root, now=now)[0]


def main() -> int:
    try:
        errors, warnings = find_issues()
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError, KeyError) as exc:
        print(f"Format freshness check could not validate artifacts: {exc}")
        return 2
    for warning in warnings:
        print(f"warning: {warning}")
    if not errors:
        return 0
    print("Current-format data is stale or inconsistent:")
    for item in errors:
        print(f"- {item}")
    print("Run python3 tools/vgc_refresh.py to re-detect the regulation and rebuild the snapshot.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
