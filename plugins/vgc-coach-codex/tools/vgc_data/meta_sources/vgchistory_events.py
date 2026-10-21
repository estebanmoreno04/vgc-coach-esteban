"""In-person official events from VGC History (primary in-person source).

Files used, as documented on https://vgchistory.com/data:
* ``/data.js``: tournament list (ruleset, dates, tier) and the species table.
* ``/standings/<id>.json``: whole-field standings with records and teams.
* ``/sheets/<id>.json``: open team sheets keyed by final placement.
* ``/matches/<id>.json``: round-by-round results, used for day 2 detection
  and team-sheet matchups.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from typing import Any
from urllib.parse import urljoin

from ..events import IN_PERSON, Event, Mon, Team
from ..http import HTTPStatusError
from ..jsliteral import extract_constant
from ..pokedex import Pokedex, clean_name
from ..text import first_date_in, normalize_regulation_id, slugify
from . import PipelineContext


SOURCE = "vgchistory"
_RECORD_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)(?:\s*-\s*(\d+))?\s*$")


def load_registry(ctx: PipelineContext) -> tuple[list[dict[str, Any]], Pokedex]:
    cfg = ctx.source(SOURCE)
    url = urljoin(cfg["base_url"], cfg["data_path"])
    source = ctx.client.get_text(url, ttl_hours=float(cfg.get("cache_ttl_hours", 24)))
    tournaments = extract_constant(source, "T")
    mons = extract_constant(source, "MONS")
    if not isinstance(tournaments, list) or not isinstance(mons, dict):
        raise ValueError("data.js does not expose T and MONS")
    return tournaments, Pokedex.from_vgchistory(mons)


def discover(ctx: PipelineContext, tournaments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tiers = {tier.lower() for tier in ctx.pipeline["in_person_tiers"]}
    found = []
    for entry in tournaments:
        if normalize_regulation_id(str(entry.get("reg", ""))) != ctx.regulation_id:
            continue
        if slugify(str(entry.get("game", ""))) != ctx.game_slug:
            continue
        if str(entry.get("tier", "")).lower() not in tiers:
            continue
        if str(entry.get("division", "Masters")).lower() != "masters":
            continue
        day = first_date_in(str(entry.get("dates", "")))
        if day is None or day > ctx.now.date():
            continue
        found.append({**entry, "_date": day})
    return sorted(found, key=lambda item: item["_date"])


def fetch(ctx: PipelineContext, entry: dict[str, Any]) -> Event:
    cfg = ctx.source(SOURCE)
    base = cfg["base_url"]
    ttl = float(cfg.get("event_cache_ttl_hours", 24))
    event_id = str(entry["id"])
    standings = json.loads(ctx.client.get_text(urljoin(base, f"standings/{event_id}.json"), ttl_hours=ttl))
    sheets = _optional_json(ctx, urljoin(base, f"sheets/{event_id}.json"), ttl) or {}
    matches = _optional_json(ctx, urljoin(base, f"matches/{event_id}.json"), ttl) or {}

    rows = standings["rows"] if isinstance(standings, dict) else standings
    teams: list[Team] = []
    index_by_player: dict[str, int] = {}
    for row in rows:
        placement, player_id, name, country, record, slugs = row[:6]
        sheet = sheets.get(str(placement)) if isinstance(sheets, dict) else None
        mons = _mons_from_sheet(ctx.pokedex, sheet) if sheet else [
            Mon(*ctx.pokedex.identity(str(slug))) for slug in slugs or []
        ]
        wins, losses, ties = _record(record)
        index_by_player[str(player_id)] = len(teams)
        teams.append(
            Team(
                placement=int(placement) if placement is not None else None,
                player_id=str(player_id),
                name=str(name),
                country=country,
                wins=wins,
                losses=losses,
                ties=ties,
                day2=None,
                mons=mons,
            )
        )

    match_rows, day2_players = _matches(matches, index_by_player)
    if day2_players is not None:
        for player_id, index in index_by_player.items():
            teams[index].day2 = player_id in day2_players

    event = Event(
        source=SOURCE,
        source_event_id=event_id,
        name=str(entry.get("full") or entry.get("name") or event_id),
        date=entry["_date"].isoformat(),
        segment=IN_PERSON,
        tier=str(entry.get("tier", "other")).lower(),
        players=int(entry.get("players") or len(teams)),
        url=urljoin(base, f"tournaments/{event_id}"),
        regulation_id=ctx.regulation_id,
        fetched_at=ctx.now,
        teams=teams,
        matches=match_rows,
        credit=cfg.get("credit"),
    )
    event.compute_coverage()
    return event


def city_key(entry: dict[str, Any]) -> tuple[date, str]:
    return entry["_date"], slugify(str(entry.get("city") or entry.get("name") or ""))


# -- helpers ---------------------------------------------------------------

def _optional_json(ctx: PipelineContext, url: str, ttl: float) -> Any:
    try:
        return json.loads(ctx.client.get_text(url, ttl_hours=ttl))
    except HTTPStatusError as exc:
        if exc.status == 404:
            return None
        raise


def _record(value: Any) -> tuple[int | None, int | None, int | None]:
    match = _RECORD_RE.match(str(value or ""))
    if not match:
        return None, None, None
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def _mons_from_sheet(dex: Pokedex, sheet: list[dict[str, Any]]) -> list[Mon]:
    mons = []
    for entry in sheet:
        item = clean_name(entry.get("item"))
        species, mega = dex.identity(str(entry.get("s", "")), item)
        dex.learn_stone(item, mega)
        mons.append(
            Mon(
                species=species,
                mega=mega,
                item=item,
                ability=clean_name(entry.get("ab")),
                nature=clean_name(entry.get("nature")),
                moves=[clean_name(move) for move in entry.get("moves") or [] if clean_name(move)],
            )
        )
    return mons


def _matches(
    payload: dict[str, Any], index_by_player: dict[str, int]
) -> tuple[list[list[int]], set[str] | None]:
    columns = payload.get("columns") or []
    rows = payload.get("matches") or []
    if not rows or "round" not in columns:
        return [], None
    col = {name: position for position, name in enumerate(columns)}
    per_round: Counter[int] = Counter()
    players_by_round: dict[int, set[str]] = {}
    result: list[list[int]] = []
    for row in rows:
        round_number = int(row[col["round"]])
        a_id = row[col["player_a_id"]]
        b_id = row[col["player_b_id"]]
        if a_id is None or b_id is None:
            continue  # bye or removed player
        per_round[round_number] += 1
        players_by_round.setdefault(round_number, set()).update({str(a_id), str(b_id)})
        a_index = index_by_player.get(str(a_id))
        b_index = index_by_player.get(str(b_id))
        if a_index is None or b_index is None:
            continue
        winner = row[col["winner"]]
        result.append([a_index, b_index, a_index if winner == "a" else b_index if winner == "b" else -1])

    # Day 2 starts at the first round with less than half the previous
    # round's matches (the field is cut overnight).
    ordered = sorted(per_round)
    day2_start = next(
        (
            current
            for previous, current in zip(ordered, ordered[1:])
            if per_round[current] < 0.5 * per_round[previous]
        ),
        None,
    )
    if day2_start is None:
        return result, None
    day2 = set()
    for round_number in ordered:
        if round_number >= day2_start:
            day2 |= players_by_round[round_number]
    return result, day2
