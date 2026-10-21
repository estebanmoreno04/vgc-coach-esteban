"""VGC History (vgchistory.com): community record of official VGC events.

``data.js`` holds a ruleset registry (``REGS``) with each ruleset's game,
Tera flag and human-readable window ("Sep 2026 – present"), plus every
tournament (``T``) with its ruleset, dates, tier and standings. The site's
data page explicitly allows reuse with credit and asks clients to cache.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urljoin

from ..jsliteral import extract_constant
from ..text import (
    end_of_day,
    first_date_in,
    normalize_regulation_id,
    parse_month_window,
    slugify,
    start_of_day,
)
from . import ReadContext, SourceReport, Window


SOURCE_ID = "vgchistory"
OFFICIAL_TIERS = {"regional", "international", "worlds", "special", "national"}


def read(context: ReadContext, cfg: dict[str, Any]) -> SourceReport:
    url = urljoin(cfg["base_url"], cfg["data_path"])
    report = SourceReport(SOURCE_ID, cfg.get("display_name", SOURCE_ID), url, "community")
    source = context.client.get_text(url, ttl_hours=float(cfg.get("cache_ttl_hours", 24)))
    regs = extract_constant(source, "REGS")
    tournaments = extract_constant(source, "T")
    if not isinstance(regs, list) or not isinstance(tournaments, list):
        raise ValueError("data.js does not expose REGS and T as arrays")

    present: list[str] = []
    for entry in regs:
        reg_id = normalize_regulation_id(str(entry.get("id", "")))
        if not reg_id:
            continue
        game = slugify(str(entry.get("game", "")))
        if game != context.game_slug:
            continue
        report.known.append(reg_id)
        report.games[reg_id] = game
        report.labels[reg_id] = str(entry.get("label") or reg_id)
        start, end, is_present = parse_month_window(str(entry.get("window", "")))
        if start is not None:
            report.windows[reg_id] = Window(
                start_of_day(start), end_of_day(end) if end else None, "month"
            )
        if is_present:
            present.append(reg_id)
        mechanics = ["terastallization"] if entry.get("tera") else []
        report.mechanics[reg_id] = mechanics

    _add_mega_evidence(report, tournaments)
    report.upcoming = [
        reg_id
        for reg_id, window in report.windows.items()
        if window.start is not None and window.start > context.now
    ]
    present = [reg_id for reg_id in present if reg_id not in report.upcoming]

    if len(present) == 1:
        report.current = present[0]
    else:
        latest = _latest_official_regulation(tournaments, context)
        if latest:
            report.current = latest
            report.notes.append("Current ruleset taken from the latest official event.")
    return report


def _add_mega_evidence(report: SourceReport, tournaments: list[dict[str, Any]]) -> None:
    """Mega Evolution is in use when standings contain '-mega' forms."""
    seen: set[str] = set()
    for tournament in tournaments:
        reg_id = normalize_regulation_id(str(tournament.get("reg", "")))
        if reg_id not in report.mechanics or reg_id in seen:
            continue
        for row in tournament.get("standings") or []:
            if any("-mega" in str(species) for species in row.get("team") or []):
                seen.add(reg_id)
                if "mega-evolution" not in report.mechanics[reg_id]:
                    report.mechanics[reg_id].append("mega-evolution")
                break


def _latest_official_regulation(
    tournaments: list[dict[str, Any]], context: ReadContext
) -> str | None:
    best: tuple[datetime, str] | None = None
    for tournament in tournaments:
        if slugify(str(tournament.get("game", ""))) != context.game_slug:
            continue
        if str(tournament.get("tier", "")).lower() not in OFFICIAL_TIERS:
            continue
        reg_id = normalize_regulation_id(str(tournament.get("reg", "")))
        day = first_date_in(str(tournament.get("dates", "")))
        if not reg_id or day is None:
            continue
        moment = start_of_day(day)
        if moment > context.now:
            continue
        if best is None or moment > best[0]:
            best = (moment, reg_id)
    return best[1] if best else None
