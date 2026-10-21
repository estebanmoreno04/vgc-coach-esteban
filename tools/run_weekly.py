#!/usr/bin/env python3
"""Weekly data refresh: the one command behind .github/workflows/weekly-refresh.yml.

Added in the estebanmoreno04 fork of NoahJenkins/vgc-coach. Runs, in order:

1. tools/vgc_refresh.py: re-detect the active regulation (archiving old data
   on a change), download new tournaments, rebuild the snapshot and the
   plugin packages;
2. tools/generate_site_trust_data.py build: refresh the site's facts;
3. tools/validate.py --scope core (skip with --no-validate).

It writes a JSON summary and a markdown report when asked, so the workflow
can commit the data and open an issue when the regulation changed.

Local use (from the repository root):

    python3 tools/run_weekly.py

Exit codes: 0 success, 1 validation failed, 2 refresh failed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_plugins  # noqa: E402
import vgc_refresh  # noqa: E402
from vgc_data.config import DEFAULT_CONFIG_PATH, REPO_ROOT, load_config  # noqa: E402
from vgc_data.http import PoliteClient  # noqa: E402
from vgc_data.text import parse_iso_z, utc_now  # noqa: E402


def issue_title(summary: dict[str, Any]) -> str | None:
    """Title of the issue to open, or None when nothing needs the owner's attention."""
    if summary.get("regulation_changed"):
        return (
            f"Regulation changed: {summary.get('previous_regulation_id')} -> "
            f"{summary['status']['regulation_id']}"
        )
    return None


def issue_body(summary: dict[str, Any], report: str) -> str:
    status = summary["status"]
    lines = [
        "The weekly refresh detected a new active regulation. The previous data was archived "
        f"to `data/archive/{summary.get('previous_regulation_id')}/` and the coach now uses "
        f"**{status['regulation_id']}**.",
        "",
        f"- Official announcement: {status.get('official_url') or 'not found'}",
        f"- Detection confidence: {status.get('confidence')}",
        "- Check that the new snapshot looks sane (early meta is expected for a few weeks).",
        "",
        report,
    ]
    return "\n".join(lines)


def commit_message(summary: dict[str, Any], date: str) -> str:
    status = summary["status"]
    if summary.get("regulation_changed"):
        return f"data: regulation changed to {status['regulation_id']} ({date})"
    new_events = len(summary.get("diff", {}).get("new_events") or [])
    return f"data: weekly refresh for {status['regulation_id']} ({date}, {new_events} new events)"


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--now", help="Override the current time (ISO-8601 UTC).")
    parser.add_argument("--no-validate", action="store_true", help="Skip tools/validate.py --scope core.")
    parser.add_argument("--summary-file", type=Path, help="Write the JSON summary here.")
    parser.add_argument("--report-file", type=Path, help="Write the markdown report here.")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    now = parse_iso_z(args.now) if args.now else utc_now()
    client = PoliteClient.from_config(config, root=REPO_ROOT)
    try:
        summary = vgc_refresh.refresh(config=config, client=client, now=now)
    except Exception as exc:  # noqa: BLE001 - any failure must stop the commit
        print(f"Refresh failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    build_plugins.build_all(REPO_ROOT)
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "generate_site_trust_data.py"), "build"],
        cwd=REPO_ROOT,
        check=True,
    )

    report = vgc_refresh.render(summary)
    date = now.date().isoformat()
    summary["issue_title"] = issue_title(summary)
    summary["issue_body"] = issue_body(summary, report) if summary["issue_title"] else None
    summary["commit_message"] = commit_message(summary, date)
    for path, content in ((args.summary_file, json.dumps(summary, indent=1, ensure_ascii=False)), (args.report_file, report)):
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content + "\n", encoding="utf-8")
    print(report)

    if args.no_validate:
        return 0
    validation = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "validate.py"), "--scope", "core"], cwd=REPO_ROOT
    )
    if validation.returncode != 0:
        print("Validation failed: do not commit this refresh.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
