#!/usr/bin/env python3
"""Refresh the coaching data and summarize what changed.

Runs tools/resolve_regulation.py (active regulation; archives the old data on
a change), then tools/build_snapshot.py (new tournaments), then rebuilds the
plugin packages so they carry the new data, and prints a summary: regulation
status, new events, usage risers and fallers, and new top cut teams.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_snapshot  # noqa: E402
import resolve_regulation  # noqa: E402
from vgc_data import query  # noqa: E402
from vgc_data.config import DEFAULT_CONFIG_PATH, REPO_ROOT, load_config  # noqa: E402
from vgc_data.http import PoliteClient, TextClient  # noqa: E402
from vgc_data.resolver import ResolutionError  # noqa: E402
from vgc_data.text import parse_iso_z, utc_now  # noqa: E402


def refresh(
    *,
    config: dict[str, Any],
    client: TextClient,
    now: datetime,
    root: Path = REPO_ROOT,
    offline: bool = False,
) -> dict[str, Any]:
    current_dir = root / config["paths"]["current_dir"]
    snapshot_path = current_dir / "snapshot.json"
    previous = json.loads(snapshot_path.read_text(encoding="utf-8")) if snapshot_path.exists() else None

    resolution = None
    if not offline:
        resolution = resolve_regulation.run(config=config, client=client, now=now, root=root)
    pipeline = build_snapshot.run(config=config, client=client, now=now, root=root, offline=offline)
    data = query.load(current_dir)
    return {
        "regulation_changed": bool(resolution and resolution.changed),
        "previous_regulation_id": resolution.previous_id if resolution and resolution.changed else None,
        "status": query.status(data, now=now),
        "regulation_warnings": (resolution.payload.get("warnings", []) if resolution else []),
        "sources": [run.to_dict() for run in pipeline.runs],
        "pipeline_warnings": pipeline.payload["warnings"],
        "diff": query.diff_snapshots(previous, pipeline.payload),
    }


def render(summary: dict[str, Any]) -> str:
    status = summary["status"]
    diff = summary["diff"]
    pct = lambda value: "n/a" if value is None else f"{100 * value:.1f}%"  # noqa: E731
    lines = [f"# VGC refresh — regulation {status['regulation_id']}"]
    if summary["regulation_changed"]:
        lines.append(
            f"**Regulation changed: {summary['previous_regulation_id']} -> {status['regulation_id']}.** "
            "The previous data was archived and is no longer used."
        )
    window = status["active_window"] or {}
    lines.append(f"- Window: {window.get('start')} -> {window.get('end')}; confidence {status['confidence']}")
    if status["next_regulation"]:
        upcoming = status["next_regulation"]
        lines.append(
            f"- Announced next: {upcoming['regulation_id']} from "
            f"{(upcoming.get('expected_window') or {}).get('start', 'unknown date')}"
        )
    segments = status["segments"] or {}
    if segments:
        lines.append(
            f"- Snapshot: {segments['in_person']['events']} in-person events "
            f"({segments['in_person']['teams']} teams), {segments['online']['events']} online events "
            f"({segments['online']['teams']} teams), data through {status['data_through']}"
        )
    lines.append("\n## New events")
    for event in diff["new_events"]:
        lines.append(f"- {event['date']} {event['name']} [{event['segment']}, {event['players']} players]")
    if not diff["new_events"]:
        lines.append("- None since the last refresh.")
    if diff["comparable"]:
        for segment, label in (("in_person", "In-person"), ("online", "Online")):
            movers = diff["movers"].get(segment) or {}
            if not movers.get("up") and not movers.get("down"):
                continue
            lines.append(f"\n## {label} usage movers (±2 points or more)")
            for item in movers.get("up", []):
                lines.append(f"- ▲ {item['name']}: {pct(item['before'])} -> {pct(item['after'])}")
            for item in movers.get("down", []):
                lines.append(f"- ▼ {item['name']}: {pct(item['before'])} -> {pct(item['after'])}")
        if diff.get("new_top_cut_teams"):
            lines.append("\n## New in-person top cut teams")
            for team in diff["new_top_cut_teams"][:16]:
                names = ", ".join(mon["mega"] or mon["name"] for mon in team["team"])
                lines.append(f"- {team['event']} #{team['placement']} {team['player']}: {names}")
    else:
        lines.append("\nNo comparable previous snapshot (first run or new regulation): no movers to report.")
    alerts = status["alerts"] + summary["regulation_warnings"] + summary["pipeline_warnings"]
    if alerts:
        lines.append("\n## Warnings")
        lines.extend(f"- {alert}" for alert in dict.fromkeys(alerts))
    errors = [f"{run['source_id']}: {error}" for run in summary["sources"] for error in run["errors"]]
    if errors:
        lines.append("\n## Source errors")
        lines.extend(f"- {error}" for error in errors[:10])
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--now", help="Override the current time (ISO-8601 UTC, for simulations).")
    parser.add_argument("--offline", action="store_true", help="Re-aggregate stored events only; no downloads.")
    parser.add_argument("--no-plugins", action="store_true", help="Do not rebuild the plugin packages.")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    config = load_config(args.config)
    now = parse_iso_z(args.now) if args.now else utc_now()
    client = PoliteClient.from_config(config, root=REPO_ROOT)
    try:
        summary = refresh(config=config, client=client, now=now, offline=args.offline)
    except (ResolutionError, build_snapshot.PipelineError, query.QueryError) as exc:
        print(f"Refresh failed: {exc}", file=sys.stderr)
        return 2
    if not args.no_plugins and (REPO_ROOT / "tools" / "build_plugins.py").exists():
        import build_plugins

        build_plugins.build_all(REPO_ROOT)
    print(json.dumps(summary, indent=1, ensure_ascii=False) if args.json else render(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
