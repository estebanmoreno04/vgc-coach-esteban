#!/usr/bin/env python3
"""Detect the active regulation and write data/current/regulation.json.

The regulation is discovered from live sources (see config/vgc-data.yaml);
nothing in the code or configuration names a regulation. When the detected
regulation differs from the stored one, the previous data in data/current is
archived to data/archive/<previous id>/.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vgc_data.config import DEFAULT_CONFIG_PATH, REPO_ROOT, load_config  # noqa: E402
from vgc_data.http import PoliteClient, TextClient  # noqa: E402
from vgc_data.resolver import (  # noqa: E402
    Resolution,
    ResolutionError,
    apply,
    load_previous,
    resolve,
)
from vgc_data.sources import ReadContext, SourceReport, run_reader  # noqa: E402
from vgc_data.sources import (  # noqa: E402
    limitless_api,
    official_news,
    pikalytics,
    vgchistory,
    victory_road,
)
from vgc_data.text import parse_iso_z, utc_now  # noqa: E402


# source id -> (reader module, kind, config key holding its URL)
READERS = {
    "official_news": (official_news, "official", "base_url"),
    "vgchistory": (vgchistory, "community", "base_url"),
    "limitless_api": (limitless_api, "community", "base_url"),
    "victory_road": (victory_road, "editorial", "url"),
    "pikalytics": (pikalytics, "supporting", "url"),
}


def collect_reports(client: TextClient, config: dict[str, Any], now: datetime) -> list[SourceReport]:
    context = ReadContext(client, config, now)
    reports = []
    for source_id, (module, kind, url_key) in READERS.items():
        source_config = config["sources"].get(source_id) or {}
        if not source_config.get("enabled", False):
            continue
        reports.append(
            run_reader(
                source_id,
                module.read,
                context,
                source_config,
                kind=kind,
                url=str(source_config.get(url_key, "")),
            )
        )
    return reports


def validate_payload(payload: dict[str, Any], schema_path: Path) -> None:
    import jsonschema

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(payload, schema)


def run(
    *,
    config: dict[str, Any],
    client: TextClient,
    now: datetime,
    root: Path = REPO_ROOT,
    dry_run: bool = False,
) -> Resolution:
    current_dir = root / config["paths"]["current_dir"]
    archive_dir = root / config["paths"]["archive_dir"]
    previous = load_previous(current_dir)
    reports = collect_reports(client, config, now)
    resolution = resolve(reports, now=now, previous=previous, game_slug=config["game"]["slug"])
    validate_payload(resolution.payload, root / config["paths"]["regulation_schema"])
    if not dry_run:
        apply(resolution, current_dir=current_dir, archive_dir=archive_dir, now=now)
    return resolution


def summarize(resolution: Resolution) -> str:
    payload = resolution.payload
    window = payload.get("active_window") or {}
    lines = [
        f"Active regulation: {payload['regulation_id']} ({payload.get('label', '')})",
        f"  game: {payload['game']}  confidence: {payload['confidence']}"
        + ("  STALE" if payload.get("stale") else ""),
        f"  window: {window.get('start')} -> {window.get('end')} "
        f"[{window.get('precision')}, {window.get('source_id')}]",
        f"  mechanics: {', '.join(payload.get('mechanics') or []) or 'none detected'}",
        f"  official: {payload.get('official_url') or 'not found'}",
        f"  agreeing sources: {', '.join(payload.get('agreeing_sources') or []) or 'none'}",
    ]
    if resolution.changed:
        lines.append(f"  CHANGED from {resolution.previous_id}")
    upcoming = payload.get("next_regulation")
    if upcoming:
        expected = upcoming.get("expected_window") or {}
        lines.append(
            f"  next: {upcoming['regulation_id']} from {expected.get('start', 'unknown date')} "
            f"({', '.join(upcoming['sources'])})"
        )
    for source in payload.get("sources", []):
        state = source["status"] if source["status"] != "ok" else f"votes {source['current_vote']}"
        lines.append(f"  - {source['source_id']}: {state}" + (f" ({source['error']})" if source.get("error") else ""))
    for warning in payload.get("warnings", []):
        lines.append(f"  ! {warning}")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--now", help="Override the current time (ISO-8601 UTC, for simulations).")
    parser.add_argument("--dry-run", action="store_true", help="Resolve without writing files.")
    parser.add_argument("--json", action="store_true", help="Print the resulting JSON payload.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    now = parse_iso_z(args.now) if args.now else utc_now()
    client = PoliteClient.from_config(config, root=REPO_ROOT)
    try:
        resolution = run(config=config, client=client, now=now, dry_run=args.dry_run)
    except ResolutionError as exc:
        print(f"Could not resolve the active regulation: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(resolution.payload, indent=2, ensure_ascii=False))
    else:
        print(summarize(resolution))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
