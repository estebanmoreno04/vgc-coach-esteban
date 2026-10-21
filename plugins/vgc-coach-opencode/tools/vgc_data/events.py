"""Normalized tournament events and their incremental on-disk store.

One file per event under data/current/events/<source>/<id>.json.gz, written
deterministically (gzip mtime 0, sorted keys) so unchanged events produce no
diff. data/current/processed_events.json records what was fetched and when,
so later runs only download events they have not processed.
"""

from __future__ import annotations

import gzip
import io
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .text import iso_z, parse_iso_z


IN_PERSON = "in_person"
ONLINE = "online"


@dataclass
class Mon:
    species: str
    mega: str | None = None
    item: str | None = None
    ability: str | None = None
    nature: str | None = None
    moves: list[str] = field(default_factory=list)

    def to_row(self) -> list[Any]:
        return [self.species, self.mega, self.item, self.ability, self.nature, list(self.moves)]

    @classmethod
    def from_row(cls, row: list[Any]) -> "Mon":
        return cls(row[0], row[1], row[2], row[3], row[4], list(row[5] or []))

    @property
    def has_set(self) -> bool:
        return bool(self.item or self.ability or self.moves)


@dataclass
class Team:
    placement: int | None
    player_id: str
    name: str
    country: str | None
    wins: int | None
    losses: int | None
    ties: int | None
    day2: bool | None
    mons: list[Mon]

    @property
    def has_record(self) -> bool:
        return self.wins is not None and self.losses is not None

    def to_row(self) -> list[Any]:
        record = [self.wins, self.losses, self.ties] if self.has_record else None
        day2 = None if self.day2 is None else int(self.day2)
        return [
            self.placement,
            self.player_id,
            self.name,
            self.country,
            record,
            day2,
            [mon.to_row() for mon in self.mons],
        ]

    @classmethod
    def from_row(cls, row: list[Any]) -> "Team":
        record = row[4] or [None, None, None]
        return cls(
            placement=row[0],
            player_id=row[1],
            name=row[2],
            country=row[3],
            wins=record[0],
            losses=record[1],
            ties=record[2],
            day2=None if row[5] is None else bool(row[5]),
            mons=[Mon.from_row(mon) for mon in row[6]],
        )


@dataclass
class Event:
    source: str
    source_event_id: str
    name: str
    date: str  # YYYY-MM-DD (first day)
    segment: str  # in_person | online
    tier: str
    players: int
    url: str
    regulation_id: str
    fetched_at: datetime
    teams: list[Team] = field(default_factory=list)
    # [team index a, team index b, winner index or -1 for a tie/double loss]
    matches: list[list[int]] = field(default_factory=list)
    coverage: dict[str, Any] = field(default_factory=dict)
    credit: str | None = None

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_event_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "source": self.source,
            "source_event_id": self.source_event_id,
            "name": self.name,
            "date": self.date,
            "segment": self.segment,
            "tier": self.tier,
            "players": self.players,
            "url": self.url,
            "regulation_id": self.regulation_id,
            "fetched_at": iso_z(self.fetched_at),
            "credit": self.credit,
            "coverage": self.coverage,
            "teams": [team.to_row() for team in self.teams],
            "matches": self.matches,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Event":
        return cls(
            source=payload["source"],
            source_event_id=payload["source_event_id"],
            name=payload["name"],
            date=payload["date"],
            segment=payload["segment"],
            tier=payload["tier"],
            players=int(payload["players"]),
            url=payload["url"],
            regulation_id=payload["regulation_id"],
            fetched_at=parse_iso_z(payload["fetched_at"]),
            teams=[Team.from_row(row) for row in payload["teams"]],
            matches=[list(match) for match in payload.get("matches", [])],
            coverage=dict(payload.get("coverage", {})),
            credit=payload.get("credit"),
        )

    def compute_coverage(self) -> None:
        teams = len(self.teams)
        self.coverage = {
            "teams": teams,
            "full_field": teams >= max(1, int(self.players * 0.9)),
            "teams_with_sets": sum(1 for team in self.teams if any(m.has_set for m in team.mons)),
            "records": teams > 0 and all(team.has_record for team in self.teams),
            "day2": any(team.day2 is not None for team in self.teams),
            "matches": len(self.matches),
        }


class EventStore:
    def __init__(self, current_dir: Path) -> None:
        self.root = current_dir / "events"
        self.index_path = current_dir / "processed_events.json"
        self.index: dict[str, dict[str, Any]] = {}
        if self.index_path.exists():
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            self.index = dict(payload.get("events", {}))
            self.regulation_id = payload.get("regulation_id")
        else:
            self.regulation_id = None

    def path_for(self, source: str, source_event_id: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in source_event_id)
        return self.root / source / f"{safe}.json.gz"

    def save(self, event: Event) -> None:
        path = self.path_for(event.source, event.source_event_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        buffer = io.BytesIO()
        with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0) as handle:
            handle.write(raw.encode("utf-8"))
        path.write_bytes(buffer.getvalue())
        self.mark(
            event.key,
            status="ok",
            fetched_at=event.fetched_at,
            segment=event.segment,
            date=event.date,
            name=event.name,
            complete=bool(event.coverage.get("teams_with_sets")) and bool(event.coverage.get("records")),
        )

    def mark(self, key: str, *, status: str, fetched_at: datetime, **extra: Any) -> None:
        entry = {"status": status, "fetched_at": iso_z(fetched_at)}
        entry.update({name: value for name, value in extra.items() if value is not None})
        self.index[key] = entry

    def remove(self, key: str) -> None:
        source, _, source_event_id = key.partition(":")
        path = self.path_for(source, source_event_id)
        if path.exists():
            path.unlink()
        self.index.pop(key, None)

    def load_all(self) -> list[Event]:
        events = []
        for key, entry in sorted(self.index.items()):
            if entry.get("status") != "ok":
                continue
            source, _, source_event_id = key.partition(":")
            path = self.path_for(source, source_event_id)
            if not path.exists():
                continue
            payload = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
            events.append(Event.from_dict(payload))
        return events

    def write_index(self, regulation_id: str) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"regulation_id": regulation_id, "events": dict(sorted(self.index.items()))}
        self.index_path.write_text(
            json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
