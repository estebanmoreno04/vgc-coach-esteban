"""Victory Road regulations page (editorial).

Each regulation has an ``<h3>`` heading followed by prose that states its
window ("... from 9 September to 2 December 2026 ..."). Dates have day
precision and no time zone.
"""

from __future__ import annotations

import re
from typing import Any

from ..text import (
    detect_mechanics,
    end_of_day,
    parse_day_month_range,
    regulation_id_in,
    start_of_day,
    strip_html,
)
from . import ReadContext, SourceReport, Window


SOURCE_ID = "victory_road"
_HEADING_RE = re.compile(r"(?is)<h3[^>]*>(.*?)</h3>")


def read(context: ReadContext, cfg: dict[str, Any]) -> SourceReport:
    url = cfg["url"]
    report = SourceReport(SOURCE_ID, cfg.get("display_name", SOURCE_ID), url, "editorial")
    markup = context.client.get_text(url, ttl_hours=float(cfg.get("cache_ttl_hours", 24)))
    headings = list(_HEADING_RE.finditer(markup))
    for index, heading in enumerate(headings):
        reg_id = regulation_id_in(strip_html(heading.group(1)))
        if not reg_id or reg_id in report.known:
            continue
        section_end = headings[index + 1].start() if index + 1 < len(headings) else len(markup)
        section = strip_html(markup[heading.end() : section_end])
        report.known.append(reg_id)
        report.labels[reg_id] = strip_html(heading.group(1))
        report.mechanics[reg_id] = detect_mechanics(section)
        for name in context.config["game"]["names"]:
            if name.lower() in section.lower():
                report.games[reg_id] = context.game_slug
                break
        start, end = parse_day_month_range(section)
        if start is None:
            continue
        window = Window(start_of_day(start), end_of_day(end) if end else None, "day")
        report.windows[reg_id] = window
        if window.contains(context.now):
            report.current = reg_id
        elif window.start is not None and window.start > context.now:
            report.upcoming.append(reg_id)
    if not report.known:
        raise ValueError("no regulation headings found")
    return report
