"""Tournament sources for the meta pipeline (tools/build_snapshot.py).

Each module discovers the events of the active regulation and turns one
event into a normalized :class:`vgc_data.events.Event`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..http import TextClient
from ..pokedex import Pokedex


@dataclass
class PipelineContext:
    client: TextClient
    config: dict[str, Any]
    now: datetime
    regulation: dict[str, Any]
    pokedex: Pokedex
    warnings: list[str] = field(default_factory=list)

    @property
    def regulation_id(self) -> str:
        return self.regulation["regulation_id"]

    @property
    def game_slug(self) -> str:
        return self.regulation.get("game") or self.config["game"]["slug"]

    @property
    def pipeline(self) -> dict[str, Any]:
        return self.config["pipeline"]

    def source(self, name: str) -> dict[str, Any]:
        return self.config["pipeline"]["sources"][name]


def tier_from_name(name: str) -> str:
    lowered = name.lower()
    if "world" in lowered:
        return "worlds"
    if "international" in lowered or any(tag in lowered for tag in ("naic", "euic", "laic", "ocic")):
        return "international"
    if "regional" in lowered:
        return "regional"
    if "special" in lowered:
        return "special"
    if "national" in lowered:
        return "nationals"
    return "other"
