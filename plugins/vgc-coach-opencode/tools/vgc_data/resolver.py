"""Combine source reports into the active regulation and manage data/current.

Decision rules
--------------
* Every reachable source casts at most one vote for the regulation it
  considers current.
* An official window (minute precision) that contains "now" is
  authoritative: it wins even against lagging community sources. It is
  ``high`` when at least two sources agree and none disagree, else ``medium``.
* Otherwise, consensus: the leading regulation has at least two votes and
  more votes than all other regulations together. Without dissent the
  confidence is ``high``; with a dissenting minority it is ``medium``.
* Conflict (no consensus, no official window): the stored regulation is kept
  (``low``); on a first run the leader is taken with ``low`` confidence.
* No reachable source: the stored regulation is kept and marked ``stale``.
* A regulation whose window has not started yet is never current; it is
  recorded as ``next_regulation``.
* When the regulation changes, everything in data/current except
  regulation.json is moved to data/archive/<previous id>/.
"""

from __future__ import annotations

import json
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .sources import PRECISION_RANK, SourceReport, Window
from .text import iso_z


SCHEMA_VERSION = "regulation-v1"
REGULATION_FILE = "regulation.json"
KIND_PRIORITY = {"official": 0, "community": 1, "editorial": 2, "supporting": 3}


class ResolutionError(RuntimeError):
    """No regulation can be determined (no sources and no stored state)."""


@dataclass
class Resolution:
    payload: dict[str, Any]
    changed: bool
    previous_id: str | None


def resolve(
    reports: Iterable[SourceReport],
    *,
    now: datetime,
    previous: dict[str, Any] | None,
    game_slug: str,
) -> Resolution:
    reports = list(reports)
    usable = [report for report in reports if report.ok]
    previous_id = (previous or {}).get("regulation_id")
    warnings: list[str] = []

    if not usable:
        if not previous_id:
            raise ResolutionError("no source could be read and there is no stored regulation")
        payload = dict(previous)
        payload.update(
            checked_at=iso_z(now),
            stale=True,
            sources=[report.summary() for report in reports],
            warnings=[
                "No source could be read; keeping the last known regulation. "
                "Data may be out of date."
            ],
        )
        return Resolution(payload, changed=False, previous_id=previous_id)

    votes: dict[str, list[str]] = {}
    for report in usable:
        if report.current:
            votes.setdefault(report.current, []).append(report.source_id)
    for reg in list(votes):
        window, window_source = _best_window(usable, reg)
        if (
            window is not None
            and window.precision != "month"
            and window.start is not None
            and window.start > now
        ):
            warnings.append(
                f"Ignoring votes for {reg} ({', '.join(sorted(votes[reg]))}): "
                f"{window_source} says it starts {iso_z(window.start)}."
            )
            del votes[reg]
    official_now = _official_current(usable, now)
    ranking = sorted(
        votes,
        key=lambda reg: (
            -len(votes[reg]),
            reg != official_now,
            reg != previous_id,
            min(_kind_rank(usable, source) for source in votes[reg]),
        ),
    )
    leader = ranking[0] if ranking else None
    leader_votes = len(votes.get(leader, [])) if leader else 0
    dissent = sum(len(votes[reg]) for reg in ranking[1:])
    consensus = leader is not None and leader_votes >= 2 and leader_votes > dissent

    if official_now:
        # The official window is authoritative; community sources may lag.
        supporters = len(votes.get(official_now, []))
        others = sum(len(sources) for reg, sources in votes.items() if reg != official_now)
        chosen = official_now
        confidence = "high" if supporters >= 2 and others == 0 else "medium"
        if others:
            warnings.append(
                f"The official window for {official_now} contains today, but other sources "
                f"still disagree: {_describe_votes(votes, exclude=official_now)}."
            )
        elif supporters < 2:
            warnings.append(
                f"Only the official source confirms {official_now}; no community source agrees yet."
            )
    elif consensus:
        chosen = leader
        confidence = "high" if dissent == 0 else "medium"
        if dissent:
            warnings.append(
                f"Minority disagreement: {_describe_votes(votes, exclude=leader)}."
            )
    elif previous_id:
        chosen = previous_id
        confidence = "low"
        if any(reg != previous_id for reg in votes):
            warnings.append(
                f"Sources disagree ({_describe_votes(votes)}); keeping {previous_id} "
                "until there is consensus or an official date confirms the change."
            )
        else:
            warnings.append(
                f"Only {leader_votes} source(s) support {previous_id}; consensus needs two."
            )
    elif leader:
        chosen = leader
        confidence = "low"
        warnings.append(
            f"First run without consensus ({_describe_votes(votes)}); provisionally using {leader}."
        )
    else:
        raise ResolutionError("no source names a current regulation")

    changed = previous_id is not None and chosen != previous_id
    window, window_source = _best_window(usable, chosen)
    if window is None:
        warnings.append(f"No source gives an active window for {chosen}.")
    elif window.end is not None and window.end < now:
        warnings.append(f"The known window for {chosen} ended {iso_z(window.end)}.")
    official_url = _first(report.official_urls.get(chosen) for report in _by_priority(usable))
    if official_url is None:
        warnings.append(f"No official announcement URL found for {chosen}.")

    detected_at = (
        (previous or {}).get("detected_at") if not changed and previous_id == chosen else None
    ) or iso_z(now)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "regulation_id": chosen,
        "label": _first(report.labels.get(chosen) for report in _by_priority(usable))
        or f"Regulation {chosen}",
        "game": _game(usable, chosen, game_slug),
        "active_window": (
            {**window.to_dict(), "source_id": window_source} if window is not None else None
        ),
        "mechanics": _mechanics(usable, chosen),
        "rules": _first(report.rules.get(chosen) for report in _by_priority(usable)) or {},
        "official_url": official_url,
        "detected_at": detected_at,
        "checked_at": iso_z(now),
        "confidence": confidence,
        "stale": False,
        "agreeing_sources": sorted(votes.get(chosen, [])),
        "previous_regulation_id": (
            previous_id if changed else (previous or {}).get("previous_regulation_id")
        ),
        "next_regulation": _next_regulation(usable, chosen, now),
        "sources": [report.summary() for report in reports],
        "warnings": warnings,
    }
    return Resolution(payload, changed=changed, previous_id=previous_id)


# -- helpers ---------------------------------------------------------------

def _kind_rank(reports: list[SourceReport], source_id: str) -> int:
    for report in reports:
        if report.source_id == source_id:
            return KIND_PRIORITY.get(report.kind, 9)
    return 9


def _by_priority(reports: list[SourceReport]) -> list[SourceReport]:
    return sorted(reports, key=lambda report: KIND_PRIORITY.get(report.kind, 9))


def _first(values: Iterable[Any]) -> Any:
    for value in values:
        if value:
            return value
    return None


def _describe_votes(votes: dict[str, list[str]], *, exclude: str | None = None) -> str:
    parts = [
        f"{reg} ({', '.join(sorted(sources))})"
        for reg, sources in sorted(votes.items())
        if reg != exclude
    ]
    return "; ".join(parts) or "no votes"


def _official_current(reports: list[SourceReport], now: datetime) -> str | None:
    matches = {
        reg
        for report in reports
        if report.kind == "official"
        for reg, window in report.windows.items()
        if window.precision == "minute" and window.contains(now)
    }
    return matches.pop() if len(matches) == 1 else None


def _best_window(reports: list[SourceReport], reg: str) -> tuple[Window | None, str | None]:
    best: tuple[int, int, Window, str] | None = None
    for report in reports:
        window = report.windows.get(reg)
        if window is None:
            continue
        key = (PRECISION_RANK.get(window.precision, 0), -KIND_PRIORITY.get(report.kind, 9))
        if best is None or key > best[:2]:
            best = (*key, window, report.source_id)
    return (best[2], best[3]) if best else (None, None)


def _game(reports: list[SourceReport], reg: str, default: str) -> str:
    counts = Counter(report.games[reg] for report in reports if reg in report.games)
    return counts.most_common(1)[0][0] if counts else default


def _mechanics(reports: list[SourceReport], reg: str) -> list[str]:
    official = [
        report.mechanics[reg]
        for report in reports
        if report.kind == "official" and reg in report.mechanics
    ]
    if official:
        return sorted(set(official[0]))
    merged: set[str] = set()
    for report in reports:
        merged.update(report.mechanics.get(reg, []))
    return sorted(merged)


def _next_regulation(
    reports: list[SourceReport], chosen: str, now: datetime
) -> dict[str, Any] | None:
    candidates: dict[str, list[str]] = {}
    for report in reports:
        for reg in report.upcoming:
            if reg != chosen:
                candidates.setdefault(reg, []).append(report.source_id)
    if not candidates:
        return None

    def start_of(reg: str) -> datetime:
        window, _ = _best_window(reports, reg)
        return window.start if window and window.start else datetime.max.replace(tzinfo=now.tzinfo)

    reg = min(candidates, key=lambda item: (start_of(item), -len(candidates[item])))
    window, window_source = _best_window(reports, reg)
    return {
        "regulation_id": reg,
        "expected_window": (
            {**window.to_dict(), "source_id": window_source} if window is not None else None
        ),
        "official_url": _first(report.official_urls.get(reg) for report in _by_priority(reports)),
        "sources": sorted(candidates[reg]),
    }


# -- data/current management ----------------------------------------------

def load_previous(current_dir: Path) -> dict[str, Any] | None:
    path = current_dir / REGULATION_FILE
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def archive_current(current_dir: Path, archive_dir: Path, previous_id: str, now: datetime) -> Path:
    """Move everything in data/current except regulation.json to the archive."""
    target = archive_dir / previous_id
    if target.exists() and any(target.iterdir()):
        target = archive_dir / f"{previous_id}-{now.strftime('%Y%m%dT%H%M%SZ')}"
    target.mkdir(parents=True, exist_ok=True)
    for entry in sorted(current_dir.iterdir()):
        if entry.name == REGULATION_FILE:
            continue
        shutil.move(str(entry), str(target / entry.name))
    previous_path = current_dir / REGULATION_FILE
    if previous_path.exists():
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
        previous["archived_at"] = iso_z(now)
        (target / REGULATION_FILE).write_text(
            json.dumps(previous, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return target


def write_regulation(current_dir: Path, payload: dict[str, Any]) -> Path:
    current_dir.mkdir(parents=True, exist_ok=True)
    path = current_dir / REGULATION_FILE
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def apply(
    resolution: Resolution, *, current_dir: Path, archive_dir: Path, now: datetime
) -> Path | None:
    """Persist a resolution. Returns the archive folder when one was created."""
    archived = None
    if resolution.changed and resolution.previous_id:
        archived = archive_current(current_dir, archive_dir, resolution.previous_id, now)
        resolution.payload.setdefault("warnings", []).append(
            f"Regulation changed from {resolution.previous_id}; previous data archived "
            f"to {archived.as_posix()}."
        )
    write_regulation(current_dir, resolution.payload)
    return archived
