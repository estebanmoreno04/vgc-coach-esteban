"""Pikalytics agent endpoint (/ai/pokedex), published for AI agents.

The page states the default (current) format, e.g.
"**Format**: <game> VGC <year> Reg X-Y" and a format code ending in "regxy".
"""

from __future__ import annotations

import re
from typing import Any

from ..text import regulation_id_from_format_code, regulation_id_in, slugify
from . import ReadContext, SourceReport


SOURCE_ID = "pikalytics"


def read(context: ReadContext, cfg: dict[str, Any]) -> SourceReport:
    url = cfg["url"]
    report = SourceReport(SOURCE_ID, cfg.get("display_name", SOURCE_ID), url, "supporting")
    text = context.client.get_text(url, ttl_hours=float(cfg.get("cache_ttl_hours", 24)))
    format_line = _field(text, "Format")
    code = _field(text, "Format Code").strip("` ")
    reg_id = regulation_id_in(format_line) or regulation_id_from_format_code(code)
    if not reg_id:
        raise ValueError("default format does not name a regulation")
    game_line = _field(text, "Game")
    if game_line and slugify(game_line) != context.game_slug:
        report.notes.append(f"Default format belongs to another game: {game_line}")
        return report
    report.current = reg_id
    report.known.append(reg_id)
    report.labels[reg_id] = format_line
    if game_line:
        report.games[reg_id] = context.game_slug
    if code:
        report.notes.append(f"Default format code: {code}")
    return report


def _field(text: str, name: str) -> str:
    match = re.search(rf"^\s*-\s*\*\*{re.escape(name)}\*\*:\s*(.+?)\s*$", text, re.MULTILINE)
    return match.group(1) if match else ""
