#!/usr/bin/env python3
"""Query the active regulation's meta snapshot (data/current) for coaching.

Examples:
  python3 tools/meta_query.py status
  python3 tools/meta_query.py usage --segment in_person --top 15
  python3 tools/meta_query.py pokemon "Kingambit"
  python3 tools/meta_query.py matchup Charizard Rillaboom
  python3 tools/meta_query.py top-cut --segment in_person --species Sneasler
  python3 tools/meta_query.py trend                  (latest regionals vs earlier ones)
  python3 tools/meta_query.py event Nice             (one event: usage, Megas, top teams)
  python3 tools/meta_query.py team --file my_team.txt     (or pipe the team on stdin)

Shares and win rates come from the snapshot built by tools/build_snapshot.py.
Use --json for machine-readable output.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vgc_data import query  # noqa: E402


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.1f}%"


def render_status(info: dict[str, Any]) -> str:
    window = info["active_window"] or {}
    lines = [
        f"## Regulation {info['regulation_id']} ({info.get('label') or ''})",
        f"- Window: {window.get('start')} -> {window.get('end')} ({window.get('precision')}, {window.get('source_id')})",
        f"- Mechanics: {', '.join(info['mechanics']) or 'none detected'}",
        f"- Official announcement: {info['official_url'] or 'not found'}",
        f"- Regulation checked: {info['regulation_checked_at']} (confidence {info['confidence']})",
    ]
    timers = (info.get("rules") or {}).get("timers_seconds")
    if timers:
        lines.append("- Timers (s): " + ", ".join(f"{key} {value}" for key, value in timers.items()))
    held = (info.get("rules") or {}).get("held_items")
    if held is not None:
        lines.append(f"- Duplicate held items allowed: {held.get('duplicates_allowed')}")
    if info["next_regulation"]:
        upcoming = info["next_regulation"]
        expected = upcoming.get("expected_window") or {}
        lines.append(f"- Next regulation: {upcoming['regulation_id']} from {expected.get('start', 'unknown date')}")
    segments = info.get("segments") or {}
    lines += [
        "",
        f"## Snapshot generated {info['snapshot_generated_at']} ({info['snapshot_age_days']} days old), data through {info['data_through']}",
    ]
    if segments:
        in_person = segments["in_person"]
        lines.append(
            f"- In-person: {in_person['events']} events, {in_person['teams']} whole-field teams, {in_person['day2_teams']} day 2 teams"
        )
        lines.append(f"- Online: {segments['online']['events']} events, {segments['online']['teams']} teams")
    lines.append(f"- Early meta: {info['early_meta']}")
    for alert in info["alerts"]:
        lines.append(f"- ALERT: {alert}")
    lines.append(f"- {info['recommendation']}")
    return "\n".join(lines)


def render_usage(rows: list[dict[str, Any]], segment: str) -> str:
    lines = [f"| # | Pokémon | {segment} share | WR | in-person day 2 conv. | online share | total share |", "|---|---|---|---|---|---|---|"]
    for index, row in enumerate(rows, start=1):
        stats = row[segment]
        lines.append(
            f"| {index} | {row['name']} | {pct(stats['share'])} ({stats['teams']}) | {pct(stats['win_rate'])} | "
            f"{pct(row['in_person']['day2_conversion'])} | {pct(row['online']['share'])} | {pct(row['total']['share'])} |"
        )
    return "\n".join(lines)


def render_pokemon(info: dict[str, Any]) -> str:
    usage = info["usage"]
    in_person = usage["in_person"]
    lines = [
        f"## {info['name']}",
        f"- In-person: {pct(in_person['share'])} of whole-field teams ({in_person['teams']}), WR {pct(in_person['win_rate'])}, "
        f"day 2 share {pct(in_person['day2_share'])}, day 2 conversion {pct(in_person['day2_conversion'])}, top cut teams {in_person['top_cut_teams']}",
        f"- Online: {pct(usage['online']['share'])} ({usage['online']['teams']}), WR {pct(usage['online']['win_rate'])}",
        f"- Total: {pct(usage['total']['share'])}, WR {pct(usage['total']['win_rate'])}",
    ]
    for mega in info["megas"]:
        lines.append(f"- {mega['name']}: in-person {pct(mega['in_person']['share'])}, online {pct(mega['online']['share'])}")
    sets = info["sets"]
    if sets:
        lines.append(f"\n### Sets (sample {sets['sample']}, in-person {sets['in_person_sample']})")
        for label in ("items", "abilities", "natures", "moves"):
            lines.append(f"- {label}: " + ", ".join(f"{item['name']} {pct(item['share'])}" for item in sets[label]))
        for spread in sets["top_sets"][:3]:
            lines.append(
                f"- {pct(spread['share'])}: {spread['item']} | {spread['ability']} | {spread['nature']} | {', '.join(spread['moves'])}"
            )
    lines.append("\n### Common partners (in-person)")
    for pair in info["pairs"]["in_person"]:
        partner = [name for name in pair["names"] if name != info["name"]]
        lines.append(f"- {' + '.join(partner)}: {pct(pair['share'])} of teams, WR {pct(pair['win_rate'])}")
    if info["best_matchups"]:
        lines.append("\n### Team-sheet matchups (in-person)")
        lines.append("- Best: " + ", ".join(f"vs {item['opponent']} {pct(item['win_rate'])} ({item['games']})" for item in info["best_matchups"]))
        lines.append("- Worst: " + ", ".join(f"vs {item['opponent']} {pct(item['win_rate'])} ({item['games']})" for item in info["worst_matchups"]))
    lines.append(f"\nTop cut appearances in the snapshot: {info['top_cut_appearances']}")
    return "\n".join(lines)


def render_top_cut(rows: list[dict[str, Any]]) -> str:
    lines = []
    for team in rows:
        lines.append(f"### {team['event']} ({team['date']}) — #{team['placement']} {team['player']} {team.get('country') or ''} {team.get('record') or ''}")
        for mon in team["team"]:
            name = mon["mega"] or mon["name"]
            moves = ", ".join(mon["moves"] or [])
            lines.append(f"- {name} @ {mon['item'] or '?'} | {mon['ability'] or '?'} | {mon['nature'] or '?'} | {moves}")
    return "\n".join(lines) or "No matching top cut teams."


def render_trend(info: dict[str, Any]) -> str:
    if not info["available"]:
        return "Not enough whole-field in-person events yet to compare recent and earlier ones."
    recent = ", ".join(f"{item['name']} ({item['date']})" for item in info["recent_events"])
    earlier = ", ".join(f"{item['name']} ({item['date']})" for item in info["earlier_events"])
    lines = [
        "## In-person trend",
        f"- Recent: {recent} — {info['recent_teams']} teams",
        f"- Earlier: {earlier} — {info['earlier_teams']} teams",
    ]
    for label, title in (("species", "Pokemon"), ("megas", "Megas")):
        for direction in ("risers", "fallers"):
            lines.append(f"\n### {title}: {direction}")
            for row in info[label][direction]:
                lines.append(
                    f"- {row['name']}: {pct(row['earlier']['share'])} -> {pct(row['recent']['share'])} "
                    f"({100 * row['share_delta']:+.1f} pts), recent WR {pct(row['recent']['win_rate'])}"
                )
    return "\n".join(lines)


def render_event(info: dict[str, Any]) -> str:
    basis = "whole field" if info["basis"] == "full_field" else "day 2 teams only"
    lines = [f"## {info['name']} ({info['date']}) — {info['players']} players, {info['teams']} teams ({basis})", "", "### Usage"]
    for index, row in enumerate(info["usage"], 1):
        lines.append(
            f"{index:>3}. {row['name']:<22} {pct(row['share']):>6}  WR {pct(row['win_rate'])}  "
            f"day 2 conv. {pct(row['day2_conversion'])}  top cut {row['top_cut_teams']}"
        )
    lines.append("\n### Megas")
    for row in info["megas"]:
        lines.append(f"- {row['name']}: {pct(row['share'])}, WR {pct(row['win_rate'])}")
    lines.append("\n" + render_top_cut(info["top_cut"]))
    return "\n".join(lines)


def render_team(info: dict[str, Any]) -> str:
    lines = ["## Team vs current meta", f"_Matchups: {info['basis']}_", ""]
    for member in info["members"]:
        if "error" in member:
            lines.append(f"- {member['input']['name']}: {member['error']}")
            continue
        usage = member["usage"]
        line = f"- **{member['name']}**" + (f" ({member['mega']})" if member["mega"] else "")
        if usage:
            line += (
                f": in-person {pct(usage['in_person']['share'])}, WR {pct(usage['in_person']['win_rate'])}, "
                f"day 2 conv. {pct(usage['in_person']['day2_conversion'])}; online {pct(usage['online']['share'])}"
            )
        lines.append(line)
        for note in member["notes"]:
            lines.append(f"  - {note}")
    lines.append("\n### Cores from this team seen in the meta (in-person)")
    for combo in info["cores_seen_in_meta"]["in_person"][:8]:
        lines.append(f"- {' + '.join(combo['names'])}: {pct(combo['share'])}, WR {pct(combo['win_rate'])}")
    lines.append("\n### Biggest threats (team-sheet WR vs this roster)")
    for threat in info["threats"]:
        lines.append(f"- {threat['name']}: {pct(threat['win_rate_vs_team'])} over {threat['games']} games")
    lines.append("\n### Most favourable common opponents")
    for item in info["favourable"]:
        lines.append(f"- {item['name']}: {pct(item['win_rate_vs_team'])} over {item['games']} games")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=query.DEFAULT_DATA_DIR)
    parser.add_argument("--json", action="store_true", help="Print JSON instead of markdown.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    usage = commands.add_parser("usage")
    usage.add_argument("--segment", choices=query.SEGMENTS, default="in_person")
    usage.add_argument("--top", type=int, default=20)
    mon = commands.add_parser("pokemon")
    mon.add_argument("name")
    pair = commands.add_parser("matchup")
    pair.add_argument("first")
    pair.add_argument("second")
    cut = commands.add_parser("top-cut")
    cut.add_argument("--segment", choices=("in_person", "online"))
    cut.add_argument("--species")
    cut.add_argument("--limit", type=int, default=16)
    commands.add_parser("events")
    trend = commands.add_parser("trend")
    trend.add_argument("--top", type=int, default=10)
    one = commands.add_parser("event")
    one.add_argument("name")
    one.add_argument("--top", type=int, default=20)
    team = commands.add_parser("team")
    team.add_argument("--file", type=Path, help="Team text file; stdin is read when omitted.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    try:
        data = query.load(args.data_dir)
        if args.command == "status":
            result: Any = query.status(data)
            text = render_status(result)
        elif args.command == "usage":
            result = query.usage(data, segment=args.segment, top=args.top)
            text = render_usage(result, args.segment)
        elif args.command == "pokemon":
            result = query.pokemon(data, args.name)
            text = render_pokemon(result)
        elif args.command == "matchup":
            result = query.matchup(data, args.first, args.second)
            text = "\n".join(
                f"- {item['species']} vs {item['opponent']}: {pct(item['win_rate'])} over {item['games']} games"
                for item in result["records"]
            ) or "Not enough games between these two in the snapshot."
        elif args.command == "top-cut":
            result = query.top_cut(data, segment=args.segment, species=args.species, limit=args.limit)
            text = render_top_cut(result)
        elif args.command == "events":
            result = query.events(data)
            text = "\n".join(
                f"- {event['date']} {event['name']} [{event['segment']}, {event['players']} players] {event['url']}"
                for event in result
            )
        elif args.command == "trend":
            result = query.trend(data, top=args.top)
            text = render_trend(result)
        elif args.command == "event":
            result = query.event(data, args.name, top=args.top)
            text = render_event(result)
        else:
            team_text = args.file.read_text(encoding="utf-8") if args.file else sys.stdin.read()
            result = query.team(data, team_text)
            text = render_team(result)
    except query.QueryError as exc:
        print(f"meta_query: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=1, ensure_ascii=False) if args.json else text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
