#!/usr/bin/env python3
"""Build the shareable coach page (a claude.ai artifact) from data/current.

Added in the estebanmoreno04 fork of NoahJenkins/vgc-coach. The page is a
chat where each visitor asks Claude with their OWN Claude account (the
artifact `sample` capability); Claude reads the meta through page functions
backed by the compact data this script embeds. Nothing here names a
regulation: everything comes from data/current/regulation.json and
snapshot.json.

    python3 tools/build_coach_page.py            # writes .artifacts/coach/coach.html

Then publish or republish the file as an artifact (ask Claude Code to do it;
the page URL is recorded in docs/fork/coach-page.md).
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vgc_data import query  # noqa: E402
from vgc_data.config import load_config  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = REPO_ROOT / "tools" / "coach_page" / "template.html"
CORE = REPO_ROOT / "tools" / "coach_page" / "core.js"
DEFAULT_OUTPUT = REPO_ROOT / ".artifacts" / "coach" / "coach.html"
PLACEHOLDER = "/*__COACH_DATA__*/null"
CORE_PLACEHOLDER = "/*__COACH_CORE__*/"
MAX_PAGE_BYTES = 15 * 1024 * 1024


def _r(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def load_sprites(cache_dir: Path, wanted: set[str]) -> dict[str, str]:
    """Base64 PNGs from the tools/fetch_sprites.py cache, for the ids the page shows."""
    manifest_path = cache_dir / "manifest.json"
    if not manifest_path.exists():
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sprites = {}
    for sprite_id in sorted(wanted):
        name = (manifest.get(sprite_id) or {}).get("file")
        if name and (cache_dir / name).exists():
            sprites[sprite_id] = base64.b64encode((cache_dir / name).read_bytes()).decode("ascii")
    return sprites


def compact(data: query.MetaData, sprite_dir: Path | None = None, sprite_credit: str | None = None) -> dict[str, Any]:
    regulation = data.regulation
    snapshot = data.snapshot
    if snapshot is None:
        raise query.QueryError("snapshot.json is missing; run tools/vgc_refresh.py first")
    usage = [
        [
            row["species"],
            row["name"],
            row["in_person"]["teams"],
            _r(row["in_person"]["share"]),
            _r(row["in_person"]["win_rate"]),
            _r(row["in_person"]["day2_share"]),
            _r(row["in_person"]["day2_conversion"]),
            row["in_person"]["top_cut_teams"],
            row["online"]["teams"],
            _r(row["online"]["share"]),
            _r(row["online"]["win_rate"]),
            _r(row["total"]["share"]),
            _r(row["total"]["win_rate"]),
        ]
        for row in snapshot["usage"]
    ]
    megas = [
        [row["mega"], row["name"], _r(row["in_person"]["share"]), _r(row["in_person"]["win_rate"]),
         _r(row["online"]["share"]), _r(row["total"]["share"])]
        for row in snapshot["megas"]
    ]

    def combos(rows: list[dict[str, Any]], limit: int) -> list[list[Any]]:
        return [[row["species"], row["names"], row["teams"], _r(row["share"]), _r(row["win_rate"])] for row in rows[:limit]]

    sets = {
        row["species"]: {
            "sample": row["sample"],
            "items": [[item["name"], _r(item["share"], 3)] for item in row["items"]],
            "abilities": [[item["name"], _r(item["share"], 3)] for item in row["abilities"]],
            "natures": [[item["name"], _r(item["share"], 3)] for item in row["natures"]],
            "moves": [[item["name"], _r(item["share"], 3)] for item in row["moves"]],
            "top_sets": [
                [spread["item"], spread["ability"], spread["nature"], spread["moves"], _r(spread["share"], 3)]
                for spread in row["top_sets"][:3]
            ],
            "day2": {
                "sample": row["day2"]["sample"],
                "items": [[item["name"], _r(item["share"], 3)] for item in row["day2"]["items"]],
                "abilities": [[item["name"], _r(item["share"], 3)] for item in row["day2"]["abilities"]],
                "natures": [[item["name"], _r(item["share"], 3)] for item in row["day2"]["natures"]],
                "moves": [[item["name"], _r(item["share"], 3)] for item in row["day2"]["moves"]],
                "top_sets": [
                    [spread["item"], spread["ability"], spread["nature"], spread["moves"], _r(spread["share"], 3)]
                    for spread in row["day2"]["top_sets"]
                ],
            },
        }
        for row in snapshot["sets"]
    }
    top_cut = [
        [
            team["segment"], team["event"], team["date"], team["placement"], team["player"], team.get("country"),
            team.get("record"),
            [[mon["mega"] or mon["name"], mon["item"], mon["ability"], mon["nature"], mon["moves"]] for mon in team["team"]],
        ]
        for team in snapshot["top_cut_teams"]
        if team["segment"] == "in_person"
    ] + [
        [
            team["segment"], team["event"], team["date"], team["placement"], team["player"], team.get("country"),
            team.get("record"),
            [[mon["mega"] or mon["name"], mon["item"], mon["ability"], mon["nature"], mon["moves"]] for mon in team["team"]],
        ]
        for team in snapshot["top_cut_teams"]
        if team["segment"] == "online"
    ][:40]
    by_event = [
        [
            event["key"], event["name"], event["date"], event["players"], event["basis"], event["teams"],
            event["day2_teams"], event["url"],
            [[row["species"], row["teams"], _r(row["share"]), _r(row["win_rate"]), _r(row["day2_conversion"]),
              row["top_cut_teams"], _r(row.get("day2_share"))] for row in event["usage"]],
            [[row["mega"], row["teams"], _r(row["share"]), _r(row["win_rate"])] for row in event["megas"]],
            event["segment"],
            [
                [team["placement"], team["player"], team.get("country"), team.get("record"),
                 [[mon["mega"] or mon["name"], mon["item"], mon["ability"], mon["nature"], mon["moves"]] for mon in team["team"]]]
                for team in event["top_teams"]
            ],
        ]
        for event in snapshot.get("by_event", [])
    ]
    trend = snapshot.get("trend") or {"available": False}

    def trend_rows(label: str) -> list[list[Any]]:
        return [
            [row["id"], _r(row["earlier"]["share"]), _r(row["recent"]["share"]), _r(row["recent"]["win_rate"]),
             row["share_delta"]]
            for row in trend.get(label, [])
        ]

    known = (
        {row[0] for row in usage} | {row[0] for row in megas}
        | {row[0] for event in by_event for row in event[8]} | {row[0] for event in by_event for row in event[9]}
    )
    dex = data.pokedex
    shown = known | {
        query_slug(mon[0]) for event in by_event for team in event[11] for mon in team[4]
    } | {query_slug(mon[0]) for team in top_cut for mon in team[7]}
    sprites = load_sprites(sprite_dir, shown) if sprite_dir else {}
    return {
        "regulation": {
            "id": regulation["regulation_id"],
            "label": regulation.get("label"),
            "window": regulation.get("active_window"),
            "mechanics": regulation.get("mechanics", []),
            "rules": regulation.get("rules", {}),
            "official_url": regulation.get("official_url"),
            "checked_at": regulation.get("checked_at"),
            "confidence": regulation.get("confidence"),
            "next": regulation.get("next_regulation"),
        },
        "snapshot": {
            "generated_at": snapshot["generated_at"],
            "data_through": snapshot["data_through"],
            "early_meta": snapshot["early_meta"],
            "early_meta_reasons": snapshot["early_meta_reasons"],
            "segments": snapshot["segments"],
            "online_window_days": snapshot["online_window_days"],
        },
        "usage": usage,
        "megas": megas,
        "pairs": {"in_person": combos(snapshot["pairs"]["in_person"], 200), "online": combos(snapshot["pairs"]["online"], 80)},
        "trios": {"in_person": combos(snapshot["trios"]["in_person"], 60)},
        "sets": sets,
        "matchups": [[row["species"], row["opponent"], row["wins"], row["games"]] for row in snapshot["matchups"]["pairs"]],
        "top_cut": top_cut,
        "events": [[event["date"], event["name"], event["segment"], event["players"], event["url"]] for event in snapshot["events"]],
        "by_event": by_event,
        "trend": {
            "available": bool(trend.get("available")),
            "recent": [[item["name"], item["date"]] for item in trend.get("recent_events", [])],
            "earlier": [[item["name"], item["date"]] for item in trend.get("earlier_events", [])],
            "recent_teams": trend.get("recent_teams", 0),
            "earlier_teams": trend.get("earlier_teams", 0),
            "species": trend_rows("species"),
            "megas": trend_rows("megas"),
        },
        "dex": {
            "names": {key: value for key, value in dex.names.items() if key in known},
            "mega_base": {key: value for key, value in dex.mega_base.items()},
            "stones": dict(dex.stones),
        },
        "credits": [source.get("credit") for source in snapshot["sources"] if source.get("credit")]
        + ([sprite_credit] if sprites and sprite_credit else []),
        "sprites": sprites,
    }


def query_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower().replace("'", "").replace(".", "")).strip("-")


def render(payload: dict[str, Any], template: str, core: str) -> str:
    if PLACEHOLDER not in template or CORE_PLACEHOLDER not in template:
        raise ValueError("template is missing a placeholder")
    if "</script" in core.lower():
        raise ValueError("core.js must not contain a closing script tag")
    # Keep the JSON safe inside a <script> element.
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return template.replace(CORE_PLACEHOLDER, core, 1).replace(PLACEHOLDER, raw, 1)


def build(data_dir: Path = query.DEFAULT_DATA_DIR, output: Path = DEFAULT_OUTPUT, *, sprites: bool = True) -> Path:
    settings = load_config().get("coach_page", {}).get("sprites", {}) if sprites else {}
    sprite_dir = REPO_ROOT / settings["cache_dir"] if settings.get("cache_dir") else None
    html = render(
        compact(query.load(data_dir), sprite_dir, settings.get("credit")),
        TEMPLATE.read_text(encoding="utf-8"),
        CORE.read_text(encoding="utf-8"),
    )
    if len(html.encode("utf-8")) > MAX_PAGE_BYTES:
        raise ValueError("coach page is too large to publish as an artifact")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=query.DEFAULT_DATA_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        path = build(args.data_dir, args.output)
    except (query.QueryError, ValueError) as exc:
        print(f"build_coach_page: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote {path} ({path.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
