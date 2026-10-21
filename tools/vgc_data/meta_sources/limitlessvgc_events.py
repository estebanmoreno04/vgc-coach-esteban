"""In-person official events from limitlessvgc.com (fallback source).

Used only for official events that VGC History does not have. The tournament
list rows carry ``data-format`` (the regulation), date, name and player
count; the teams page lists the day 2 (phase 2) team sheets with item,
ability, nature and moves, but no records.
"""

from __future__ import annotations

import html
import re
from datetime import date
from typing import Any
from urllib.parse import urljoin

from ..events import IN_PERSON, Event, Mon, Team
from ..pokedex import clean_name, slug
from ..text import normalize_regulation_id, strip_html
from . import PipelineContext, tier_from_name


SOURCE = "limitlessvgc"
_ROW_RE = re.compile(r"(?is)<tr\s+([^>]*data-date=[^>]*)>(.*?)</tr>")
_ATTR_RE = re.compile(r'data-([a-z]+)="([^"]*)"')
_LINK_RE = re.compile(r'href="/tournaments/(\d+)"')
_TEAM_RE = re.compile(
    r'(?is)<div class="teamlist-toggle"[^>]*>\s*(\d+)(?:st|nd|rd|th)\s+(.*?)</div>(.*?)(?=<div class="teamlist-toggle"|</section>)'
)
_MON_RE = re.compile(r'(?is)<div class="pkmn" data-id="([^"]+)">(.*?)</ul>')


def discover(ctx: PipelineContext) -> list[dict[str, Any]]:
    cfg = ctx.source(SOURCE)
    url = urljoin(cfg["base_url"], "tournaments")
    markup = ctx.client.get_text(url, ttl_hours=float(cfg.get("cache_ttl_hours", 24)))
    found = []
    for attributes, body in _ROW_RE.findall(markup):
        attrs = {key: html.unescape(value) for key, value in _ATTR_RE.findall(attributes)}
        link = _LINK_RE.search(body)
        if not link or normalize_regulation_id(attrs.get("format", "")) != ctx.regulation_id:
            continue
        day = date.fromisoformat(attrs["date"])
        if day > ctx.now.date():
            continue
        found.append(
            {
                "id": link.group(1),
                "name": attrs.get("name", link.group(1)),
                "_date": day,
                "players": int(attrs.get("players") or 0),
                "country": attrs.get("country"),
            }
        )
    return found


def matches_known_event(entry: dict[str, Any], known: list[tuple[date, str]]) -> bool:
    """True when VGC History already has this event (same dates, same city)."""
    name = slug(entry["name"])
    for known_date, city in known:
        if city and abs((known_date - entry["_date"]).days) <= 1 and city in name:
            return True
    return False


def fetch(ctx: PipelineContext, entry: dict[str, Any]) -> Event:
    cfg = ctx.source(SOURCE)
    url = urljoin(cfg["base_url"], f"tournaments/{entry['id']}/teams")
    markup = ctx.client.get_text(url, ttl_hours=float(cfg.get("event_cache_ttl_hours", 24)))
    teams: list[Team] = []
    for placement, player, body in _TEAM_RE.findall(markup):
        mons = [_mon(ctx, data_id, block) for data_id, block in _MON_RE.findall(body)]
        if not mons:
            continue
        name = strip_html(player)
        teams.append(
            Team(
                placement=int(placement),
                player_id=slug(name),
                name=name,
                country=None,
                wins=None,
                losses=None,
                ties=None,
                day2=True,
                mons=mons,
            )
        )
    if not teams:
        raise ValueError(f"{url}: no team lists found")
    event = Event(
        source=SOURCE,
        source_event_id=str(entry["id"]),
        name=entry["name"],
        date=entry["_date"].isoformat(),
        segment=IN_PERSON,
        tier=tier_from_name(entry["name"]),
        players=entry["players"] or len(teams),
        url=urljoin(cfg["base_url"], f"tournaments/{entry['id']}"),
        regulation_id=ctx.regulation_id,
        fetched_at=ctx.now,
        teams=teams,
        credit=cfg.get("credit"),
    )
    event.compute_coverage()
    event.coverage["day2_only"] = True
    return event


def _mon(ctx: PipelineContext, data_id: str, block: str) -> Mon:
    item = clean_name(_field(block, "item"))
    ability = clean_name(re.sub(r"(?i)^ability:\s*", "", _field(block, "ability") or "")) or None
    nature = clean_name(re.sub(r"(?i)\s*nature$", "", _field(block, "nature") or "")) or None
    moves = [clean_name(strip_html(move)) for move in re.findall(r"(?is)<li>(.*?)</li>", block)]
    species, mega = ctx.pokedex.identity(data_id, item)
    return Mon(species, mega, item, ability, nature, [move for move in moves if move])


def _field(block: str, css_class: str) -> str | None:
    match = re.search(rf'(?is)<div class="{css_class}">(.*?)</div>', block)
    return strip_html(match.group(1)) if match else None
