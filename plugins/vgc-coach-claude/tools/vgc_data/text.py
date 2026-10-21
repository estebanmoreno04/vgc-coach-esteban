"""Text helpers: regulation id normalization, dates, slugs and mechanics.

These helpers recognise the *shape* of regulation identifiers ("Regulation
Set X-Y", "Reg X-Y", format codes ending in ``regxy``) without knowing any
specific identifier.
"""

from __future__ import annotations

import calendar
import html
import re
import unicodedata
from datetime import date, datetime, time, timedelta, timezone


_DASHES = "-‐‑‒–—"
_REGULATION_RE = re.compile(
    r"(?<![A-Za-z])[Rr]eg(?:ulation)?\.?\s+(?:[Ss]et\s+)?"
    rf"([A-Z])(?:\s?[{_DASHES}]\s?([A-Z0-9]))?(?![A-Za-z0-9])"
)
_FORMAT_CODE_RE = re.compile(r"reg([a-z])([a-z0-9])?(?:bo\d)?$")

_MONTHS = {
    name.lower(): index
    for index, name in enumerate(calendar.month_name)
    if name
}
_MONTHS.update(
    {name.lower(): index for index, name in enumerate(calendar.month_abbr) if name}
)
_MONTHS["sept"] = 9
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))

# Keyword -> mechanic slug. Mechanic names are generic game concepts, not
# regulation identifiers.
_MECHANIC_KEYWORDS = (
    (re.compile(r"\bmega[\s-]?evol", re.IGNORECASE), "mega-evolution"),
    (re.compile(r"\bterastal", re.IGNORECASE), "terastallization"),
    (re.compile(r"\bdynamax|\bgigantamax", re.IGNORECASE), "dynamax"),
    (re.compile(r"\bz-?moves?\b|\bz-?crystal", re.IGNORECASE), "z-moves"),
)
_NEGATION_RE = re.compile(
    r"\b(?:not|no|cannot|can't|can’t|isn't|isn’t|aren't|aren’t|won't|won’t|banned|prohibited)\b",
    re.IGNORECASE,
)
_CLAUSE_BREAK_RE = re.compile(r"[.;,\n]|\bbut\b|\bwhile\b|\bwhereas\b", re.IGNORECASE)


def regulation_ids_in(text: str) -> list[str]:
    """Return every regulation id mentioned in ``text``, in order, deduplicated."""
    found: list[str] = []
    for match in _REGULATION_RE.finditer(text or ""):
        major, minor = match.group(1), match.group(2)
        reg_id = f"{major}-{minor}" if minor else major
        if reg_id not in found:
            found.append(reg_id)
    return found


def regulation_id_in(text: str) -> str | None:
    found = regulation_ids_in(text)
    return found[0] if found else None


def regulation_id_from_format_code(code: str) -> str | None:
    """Read a regulation id from a format code such as ``...2026regxy``."""
    match = _FORMAT_CODE_RE.search((code or "").strip().lower())
    if not match:
        return None
    major, minor = match.group(1).upper(), match.group(2)
    return f"{major}-{minor.upper()}" if minor else major


def normalize_regulation_id(value: str) -> str | None:
    """Normalize a bare id ("X-Y", "x‑y", "XY" is not accepted) or a phrase."""
    value = (value or "").strip()
    bare = re.fullmatch(rf"([A-Za-z])\s?[{_DASHES}]\s?([A-Za-z0-9])", value)
    if bare:
        return f"{bare.group(1).upper()}-{bare.group(2).upper()}"
    if re.fullmatch(r"[A-Z]", value):
        return value
    return regulation_id_in(value)


def slugify(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value or "")
    ascii_text = folded.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")


def strip_html(markup: str) -> str:
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", markup or "")
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|h\d|li|tr)>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text).replace("​", "").replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*", "\n", text).strip()


def month_number(name: str) -> int | None:
    return _MONTHS.get((name or "").strip().rstrip(".").lower())


def detect_mechanics(text: str) -> list[str]:
    """Detect battle mechanics described as allowed in ``text``."""
    found: list[str] = []
    text = text or ""
    breaks = [match.start() for match in _CLAUSE_BREAK_RE.finditer(text)]
    for pattern, slug in _MECHANIC_KEYWORDS:
        for match in pattern.finditer(text):
            clause_start = max((cut for cut in breaks if cut < match.start()), default=0)
            clause_end = min((cut for cut in breaks if cut >= match.end()), default=len(text))
            if _NEGATION_RE.search(text[clause_start:clause_end]):
                continue
            if slug not in found:
                found.append(slug)
            break
    return found


# --------------------------------------------------------------------------
# Dates

def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso_z(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def parse_iso_z(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def start_of_day(day: date) -> datetime:
    return datetime.combine(day, time(0, 0), tzinfo=timezone.utc)


def end_of_day(day: date) -> datetime:
    return datetime.combine(day, time(23, 59, 59), tzinfo=timezone.utc)


def first_date_in(text: str) -> date | None:
    """Parse the first date of strings like 'October 17–18, 2026' or 'Oct 31 – Nov 1, 2026'."""
    match = re.search(
        rf"\b({_MONTH_RE})\.?\s+(\d{{1,2}})\b.*?\b(\d{{4}})\b", text or "", re.IGNORECASE
    )
    if match:
        month = month_number(match.group(1))
        if month:
            return date(int(match.group(3)), month, int(match.group(2)))
    match = re.search(
        rf"\b(\d{{1,2}})\s+({_MONTH_RE})\.?\b.*?\b(\d{{4}})\b", text or "", re.IGNORECASE
    )
    if match:
        month = month_number(match.group(2))
        if month:
            return date(int(match.group(3)), month, int(match.group(1)))
    return None


def parse_day_month_range(text: str) -> tuple[date | None, date | None]:
    """Parse 'from 9 September to 2 December 2026' (Victory Road style).

    Also accepts 'from 9 September 2026' with no end. The start year defaults
    to the end year and rolls back one year when the range crosses January.
    """
    month = _MONTH_RE
    ranged = re.search(
        rf"\bfrom\s+(\d{{1,2}})\s+({month})(?:\s+(\d{{4}}))?\s+(?:to|until|through|–|-)\s+"
        rf"(\d{{1,2}})\s+({month})\s+(\d{{4}})",
        text or "",
        re.IGNORECASE,
    )
    if ranged:
        end = date(int(ranged.group(6)), month_number(ranged.group(5)), int(ranged.group(4)))
        start_month = month_number(ranged.group(2))
        start_year = int(ranged.group(3)) if ranged.group(3) else end.year
        if not ranged.group(3) and start_month > end.month:
            start_year -= 1
        return date(start_year, start_month, int(ranged.group(1))), end
    open_ended = re.search(
        rf"\b(?:from|starting(?: on)?|begins(?: on)?)\s+(\d{{1,2}})\s+({month})\s+(\d{{4}})",
        text or "",
        re.IGNORECASE,
    )
    if open_ended:
        return (
            date(int(open_ended.group(3)), month_number(open_ended.group(2)), int(open_ended.group(1))),
            None,
        )
    return None, None


def parse_utc_duration(text: str) -> tuple[datetime | None, datetime | None]:
    """Parse 'June 17, 2026, at 02:00 UTC to ... September 9, 2026, at 01:59 UTC'."""
    stamp = rf"({_MONTH_RE})\s+(\d{{1,2}}),\s+(\d{{4}}),?\s+at\s+(\d{{1,2}}):(\d{{2}})\s*UTC"
    match = re.search(rf"{stamp}.*?\bto\b.*?{stamp}", text or "", re.IGNORECASE | re.DOTALL)
    if match:
        return _stamp(match.groups()[:5]), _stamp(match.groups()[5:])
    single = re.search(stamp, text or "", re.IGNORECASE)
    if single:
        return _stamp(single.groups()), None
    return None, None


def _stamp(parts: tuple[str, ...]) -> datetime:
    month, day, year, hour, minute = parts
    return datetime(
        int(year), month_number(month), int(day), int(hour), int(minute), tzinfo=timezone.utc
    )


def parse_month_window(text: str) -> tuple[date | None, date | None, bool]:
    """Parse 'Sep 2026 – present' or 'Jun 2026 – Sep 2026' (month precision).

    Returns (first day of start month, last day of end month, is_present).
    When the text lists several spans ('..., then Dec 2025 – Apr 2026') the
    last span is used.
    """
    spans = re.findall(
        rf"({_MONTH_RE})\.?\s+(\d{{4}})\s*[{_DASHES}]\s*(present|({_MONTH_RE})\.?\s+(\d{{4}}))",
        text or "",
        re.IGNORECASE,
    )
    if not spans:
        return None, None, False
    start_month, start_year, tail, end_month, end_year = spans[-1]
    start = date(int(start_year), month_number(start_month), 1)
    if tail.lower() == "present":
        return start, None, True
    month = month_number(end_month)
    last_day = calendar.monthrange(int(end_year), month)[1]
    return start, date(int(end_year), month, last_day), False


def days_ago(now: datetime, days: int) -> datetime:
    return now - timedelta(days=days)
