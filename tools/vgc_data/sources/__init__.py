"""Source adapters for the regulation resolver.

Each adapter reads one source and returns a :class:`SourceReport` with what
that source says about regulations: which one is current, which are
upcoming, dated windows, mechanics, game and official links. Adapters never
decide anything; :mod:`vgc_data.resolver` combines the reports.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Callable

from ..http import SourceBlocked, SourceError, TextClient
from ..text import iso_z


PRECISION_RANK = {"minute": 3, "day": 2, "month": 1}


@dataclass
class Window:
    start: datetime | None
    end: datetime | None
    precision: str  # minute | day | month

    def contains(self, moment: datetime) -> bool:
        if self.start is not None and moment < self.start:
            return False
        if self.end is not None and moment > self.end:
            return False
        return self.start is not None

    def to_dict(self) -> dict[str, Any]:
        return {"start": iso_z(self.start), "end": iso_z(self.end), "precision": self.precision}


@dataclass
class SourceReport:
    source_id: str
    display_name: str
    url: str
    kind: str  # official | community | supporting | editorial
    status: str = "ok"  # ok | error | blocked
    error: str | None = None
    fetched_at: datetime | None = None
    current: str | None = None
    upcoming: list[str] = field(default_factory=list)
    known: list[str] = field(default_factory=list)
    windows: dict[str, Window] = field(default_factory=dict)
    mechanics: dict[str, list[str]] = field(default_factory=dict)
    games: dict[str, str] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    official_urls: dict[str, str] = field(default_factory=dict)
    rules: dict[str, dict[str, Any]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def summary(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "display_name": self.display_name,
            "kind": self.kind,
            "url": self.url,
            "status": self.status,
            "error": self.error,
            "fetched_at": iso_z(self.fetched_at),
            "current_vote": self.current,
            "upcoming": list(self.upcoming),
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class ReadContext:
    client: TextClient
    config: dict[str, Any]
    now: datetime

    @property
    def game_slug(self) -> str:
        return self.config["game"]["slug"]

    @property
    def resolver(self) -> dict[str, Any]:
        return self.config["resolver"]


Reader = Callable[[ReadContext, dict[str, Any]], SourceReport]


def run_reader(
    source_id: str,
    reader: Reader,
    context: ReadContext,
    source_config: dict[str, Any],
    *,
    kind: str,
    url: str,
) -> SourceReport:
    """Run one adapter and turn any failure into an error report."""
    display_name = source_config.get("display_name", source_id)
    try:
        report = reader(context, source_config)
    except SourceBlocked as exc:
        return SourceReport(source_id, display_name, url, kind, status="blocked", error=str(exc))
    except (SourceError, ValueError, KeyError, TypeError) as exc:
        return SourceReport(
            source_id, display_name, url, kind, status="error", error=f"{type(exc).__name__}: {exc}"
        )
    report.fetched_at = report.fetched_at or context.now
    return report


def report_to_dict(report: SourceReport) -> dict[str, Any]:
    payload = asdict(report)
    payload["windows"] = {key: window.to_dict() for key, window in report.windows.items()}
    payload["fetched_at"] = iso_z(report.fetched_at)
    return payload
