"""Limitless tournament platform API (play.limitlesstcg.com/api).

Documented, keyless API (rate limited to 50 requests per 5 minutes). Every
tournament carries a ``format`` id; ``/games`` maps those ids to names such
as "Regulation Set X-Y". The vote is the format used by most recent large
tournaments.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from typing import Any
from urllib.parse import urlencode, urljoin

from ..text import days_ago, normalize_regulation_id, parse_iso_z, regulation_id_in
from . import ReadContext, SourceReport


SOURCE_ID = "limitless_api"


def read(context: ReadContext, cfg: dict[str, Any]) -> SourceReport:
    base_url = cfg["base_url"]
    ttl = float(cfg.get("cache_ttl_hours", 6))
    games_url = urljoin(base_url, "games")
    report = SourceReport(SOURCE_ID, cfg.get("display_name", SOURCE_ID), base_url, "community")

    format_ids = _format_map(json.loads(context.client.get_text(games_url, ttl_hours=ttl)), cfg)
    report.known = sorted(set(format_ids.values()))

    since = days_ago(context.now, int(context.resolver["recent_window_days"]))
    min_players = int(context.resolver["min_players"])
    counts: Counter[str] = Counter()
    for page in range(1, int(cfg.get("max_pages", 5)) + 1):
        query = urlencode({"game": cfg["game_id"], "limit": cfg.get("page_size", 100), "page": page})
        batch = json.loads(
            context.client.get_text(urljoin(base_url, f"tournaments?{query}"), ttl_hours=ttl)
        )
        if not isinstance(batch, list) or not batch:
            break
        oldest: datetime | None = None
        for tournament in batch:
            when = parse_iso_z(str(tournament.get("date") or "")) if tournament.get("date") else None
            if when is None:
                continue
            oldest = when if oldest is None or when < oldest else oldest
            if when < since or when > context.now:
                continue
            if int(tournament.get("players") or 0) < min_players:
                continue
            reg_id = format_ids.get(str(tournament.get("format")))
            if reg_id:
                counts[reg_id] += 1
        if oldest is not None and oldest < since:
            break

    if counts:
        (leader, leader_count), *rest = counts.most_common()
        report.notes.append(
            "Large recent tournaments by format: "
            + ", ".join(f"{reg} x{count}" for reg, count in counts.most_common())
        )
        if leader_count >= int(context.resolver["min_tournaments"]) and (
            not rest or leader_count > rest[0][1]
        ):
            report.current = leader
    else:
        report.notes.append("No large tournaments in the recent window.")
    return report


def _format_map(games: Any, cfg: dict[str, Any]) -> dict[str, str]:
    for game in games if isinstance(games, list) else []:
        if str(game.get("id")) != cfg["game_id"]:
            continue
        mapping: dict[str, str] = {}
        for key, name in (game.get("formats") or {}).items():
            reg_id = regulation_id_in(str(name)) or normalize_regulation_id(str(key))
            if reg_id:
                mapping[str(key)] = reg_id
        return mapping
    raise ValueError(f"game {cfg['game_id']!r} not listed by /games")
