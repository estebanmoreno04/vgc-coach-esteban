"""Online tournaments from the Limitless API (play.limitlesstcg.com/api).

Only tournaments of the active regulation, with at least ``min_players``
players, inside the online window, played online and with public team lists
are kept. In-person locals hosted on Limitless are skipped: the in-person
segment is reserved for official events.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode, urljoin

from ..events import ONLINE, Event, Mon, Team
from ..pokedex import clean_name
from ..text import days_ago, normalize_regulation_id, parse_iso_z, regulation_id_in
from . import PipelineContext


SOURCE = "limitless_api"


def format_key(ctx: PipelineContext) -> str | None:
    cfg = ctx.source(SOURCE)
    games = json.loads(
        ctx.client.get_text(urljoin(cfg["base_url"], "games"), ttl_hours=float(cfg.get("cache_ttl_hours", 6)))
    )
    for game in games:
        if str(game.get("id")) != cfg["game_id"]:
            continue
        for key, name in (game.get("formats") or {}).items():
            if (regulation_id_in(str(name)) or normalize_regulation_id(str(key))) == ctx.regulation_id:
                return str(key)
    return None


def discover(ctx: PipelineContext, key: str) -> list[dict[str, Any]]:
    cfg = ctx.source(SOURCE)
    since = days_ago(ctx.now, int(ctx.pipeline["online_window_days"]))
    min_players = int(ctx.pipeline["online_min_players"])
    found: list[dict[str, Any]] = []
    for page in range(1, int(cfg.get("max_pages", 10)) + 1):
        query = urlencode({"game": cfg["game_id"], "format": key, "limit": cfg.get("page_size", 100), "page": page})
        batch = json.loads(
            ctx.client.get_text(urljoin(cfg["base_url"], f"tournaments?{query}"), ttl_hours=float(cfg.get("cache_ttl_hours", 6)))
        )
        if not isinstance(batch, list) or not batch:
            break
        oldest = None
        for tournament in batch:
            when = parse_iso_z(str(tournament.get("date") or "")) if tournament.get("date") else None
            if when is None:
                continue
            oldest = when if oldest is None or when < oldest else oldest
            if str(tournament.get("format")) != key:
                continue  # never mix formats, even if the API filter is ignored
            if since <= when <= ctx.now and int(tournament.get("players") or 0) >= min_players:
                found.append({**tournament, "_when": when})
        if oldest is not None and oldest < since:
            break
    return sorted(found, key=lambda item: item["_when"])


def fetch(ctx: PipelineContext, entry: dict[str, Any]) -> tuple[Event | None, str | None]:
    """Return (event, None) or (None, reason it was skipped)."""
    cfg = ctx.source(SOURCE)
    base = cfg["base_url"]
    tournament_id = str(entry["id"])
    details = json.loads(ctx.client.get_text(urljoin(base, f"tournaments/{tournament_id}/details")))
    if details.get("isOnline") is False:
        return None, "in-person local event (not an official in-person tournament)"
    if not details.get("decklists"):
        return None, "no public team lists"
    standings = json.loads(ctx.client.get_text(urljoin(base, f"tournaments/{tournament_id}/standings")))
    teams = []
    for player in standings:
        decklist = player.get("decklist") or []
        if not decklist:
            continue
        mons = []
        for mon in decklist:
            item = clean_name(mon.get("item"))
            species, mega = ctx.pokedex.identity(str(mon.get("id") or mon.get("name") or ""), item)
            mons.append(
                Mon(
                    species=species,
                    mega=mega,
                    item=item,
                    ability=clean_name(mon.get("ability")),
                    nature=clean_name(mon.get("nature")),
                    moves=[clean_name(move) for move in mon.get("attacks") or [] if clean_name(move)],
                )
            )
        record = player.get("record") or {}
        teams.append(
            Team(
                placement=player.get("placing"),
                player_id=str(player.get("player")),
                name=str(player.get("name") or player.get("player")),
                country=player.get("country"),
                wins=_int(record.get("wins")),
                losses=_int(record.get("losses")),
                ties=_int(record.get("ties")) or 0,
                day2=None,
                mons=mons,
            )
        )
    if not teams:
        return None, "standings without team lists"
    event = Event(
        source=SOURCE,
        source_event_id=tournament_id,
        name=str(entry.get("name") or tournament_id),
        date=entry["_when"].date().isoformat(),
        segment=ONLINE,
        tier="online",
        players=int(entry.get("players") or len(teams)),
        url=f"https://play.limitlesstcg.com/tournament/{tournament_id}/standings",
        regulation_id=ctx.regulation_id,
        fetched_at=ctx.now,
        teams=teams,
        credit=cfg.get("credit"),
    )
    event.compute_coverage()
    return event, None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
