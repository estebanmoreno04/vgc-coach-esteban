"""Official Pokémon Champions in-game news (champions-news.pokemon-home.com).

The news index is a JSON list. Regulation announcements carry the category
label configured in ``category_label``; their article pages state the exact
UTC duration, the allowed mechanics, held-item rules and timers.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

from ..text import detect_mechanics, parse_utc_duration, regulation_id_in, strip_html
from . import ReadContext, SourceReport, Window


SOURCE_ID = "official_news"
_TIMER_LABELS = {
    "total time": "match",
    "player time": "player",
    "turn time": "turn",
    "preview time": "team_preview",
}


def read(context: ReadContext, cfg: dict[str, Any]) -> SourceReport:
    base_url = cfg["base_url"]
    list_url = urljoin(base_url, cfg["list_path"])
    ttl = float(cfg.get("cache_ttl_hours", 168))
    report = SourceReport(SOURCE_ID, cfg.get("display_name", SOURCE_ID), list_url, "official")

    payload = json.loads(context.client.get_text(list_url, ttl_hours=ttl))
    entries = [
        entry
        for entry in payload.get("data", [])
        if str(entry.get("kindTxt", "")).strip().lower() == cfg["category_label"].lower()
    ]
    announcements: list[tuple[str, dict[str, Any]]] = []
    for entry in entries:
        reg_id = regulation_id_in(str(entry.get("title", "")))
        if reg_id and reg_id not in report.known:
            report.known.append(reg_id)
            announcements.append((reg_id, entry))

    # Read only announcements whose news item has not expired: the current
    # regulation and any announced one. Older articles are history.
    live = [
        (reg_id, entry)
        for reg_id, entry in announcements
        if _expires_at(entry) is None or _expires_at(entry) >= context.now
    ]
    live.sort(key=lambda item: int(item[1].get("pubAt") or 0), reverse=True)
    for reg_id, entry in live[: int(cfg.get("max_articles", 3))]:
        article_url = urljoin(base_url, str(entry["link"]))
        report.official_urls[reg_id] = article_url
        report.labels[reg_id] = re.sub(r"\s*\(.*?\)\s*$", "", str(entry.get("title", ""))).strip()
        _read_article(context, report, reg_id, article_url, ttl)

    for reg_id, window in report.windows.items():
        if window.contains(context.now):
            report.current = reg_id
        elif window.start is not None and window.start > context.now:
            report.upcoming.append(reg_id)
    if report.current is None:
        report.notes.append("No official regulation window contains the current date.")
    return report


def _read_article(
    context: ReadContext, report: SourceReport, reg_id: str, url: str, ttl: float
) -> None:
    markup = context.client.get_text(url, ttl_hours=ttl)
    body = _article_body(markup)
    text = strip_html(body)
    start, end = parse_utc_duration(text)
    if start is None:
        report.notes.append(f"{reg_id}: article does not state a UTC duration.")
    else:
        report.windows[reg_id] = Window(start, end, "minute")
    mechanics_text = _section(body, "Mechanics") or text
    report.mechanics[reg_id] = detect_mechanics(strip_html(mechanics_text))
    for name in context.config["game"]["names"]:
        if name.lower() in text.lower():
            report.games[reg_id] = context.game_slug
            break
    rules: dict[str, Any] = {}
    items_text = strip_html(_section(body, "Held Items") or "")
    if items_text:
        lowered = items_text.lower()
        if "not allowed" in lowered:
            rules["held_items"] = {"duplicates_allowed": False}
        elif "allowed" in lowered:
            rules["held_items"] = {"duplicates_allowed": True}
    timers = _timers(strip_html(_section(body, "Timers") or ""))
    if timers:
        rules["timers_seconds"] = timers
    if rules:
        report.rules[reg_id] = rules


def _expires_at(entry: dict[str, Any]) -> datetime | None:
    raw = entry.get("endAt")
    try:
        return datetime.fromtimestamp(int(raw), timezone.utc)
    except (TypeError, ValueError):
        return None


def _article_body(markup: str) -> str:
    match = re.search(r'(?is)<div class="article-body">(.*?)</article>', markup)
    return match.group(1) if match else markup


def _section(body: str, heading: str) -> str | None:
    match = re.search(
        rf"(?is)<h[12][^>]*>\s*{re.escape(heading)}\s*</h[12]>(.*?)(?=<h[12][^>]*>|$)", body
    )
    return match.group(1) if match else None


def _timers(text: str) -> dict[str, int]:
    timers: dict[str, int] = {}
    for label, key in _TIMER_LABELS.items():
        match = re.search(rf"{label}\s*:\s*(\d+)\s*(minute|second)", text, re.IGNORECASE)
        if match:
            value = int(match.group(1))
            timers[key] = value * 60 if match.group(2).lower() == "minute" else value
    return timers
