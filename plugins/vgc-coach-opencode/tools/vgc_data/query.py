"""Read-only queries over data/current (regulation.json + snapshot.json).

This module is the single way coaching surfaces read the meta: the skills
call it through tools/meta_query.py, tools/vgc_refresh.py uses it to
summarize changes, and any future front end (a chatbot, a web page) can
import it. It never reads data/archive/: archived regulations are history.
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .pokedex import Pokedex, slug


DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "current"
MAX_SNAPSHOT_AGE_DAYS = 7
SEGMENTS = ("in_person", "online", "total")


class QueryError(RuntimeError):
    """The data needed for a query is missing or a name cannot be resolved."""


@dataclass
class MetaData:
    regulation: dict[str, Any]
    snapshot: dict[str, Any] | None
    pokedex: Pokedex
    data_dir: Path


def load(data_dir: Path = DEFAULT_DATA_DIR) -> MetaData:
    data_dir = Path(data_dir)
    if "archive" in {part.lower() for part in data_dir.resolve().parts}:
        raise QueryError("data/archive holds past regulations and must not be used for coaching")
    regulation_path = data_dir / "regulation.json"
    if not regulation_path.exists():
        raise QueryError(f"{regulation_path} is missing; run tools/vgc_refresh.py")
    regulation = json.loads(regulation_path.read_text(encoding="utf-8"))
    snapshot_path = data_dir / "snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8")) if snapshot_path.exists() else None
    if snapshot and snapshot["regulation"]["regulation_id"] != regulation["regulation_id"]:
        raise QueryError(
            f"snapshot.json is for {snapshot['regulation']['regulation_id']} but the active regulation "
            f"is {regulation['regulation_id']}; run tools/vgc_refresh.py"
        )
    return MetaData(regulation, snapshot, Pokedex.load(data_dir / "pokedex.json"), data_dir)


def _require_snapshot(data: MetaData) -> dict[str, Any]:
    if not data.snapshot:
        raise QueryError("snapshot.json is missing for the active regulation; run tools/vgc_refresh.py")
    return data.snapshot


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


# -- status ----------------------------------------------------------------------

def status(data: MetaData, *, now: datetime | None = None, max_age_days: int = MAX_SNAPSHOT_AGE_DAYS) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    regulation = data.regulation
    snapshot = data.snapshot
    window = regulation.get("active_window") or {}
    end = _parse(window.get("end"))
    alerts: list[str] = []
    if regulation.get("stale"):
        alerts.append("The active regulation could not be re-checked (all sources failed); it may be out of date.")
    if regulation.get("confidence") == "low":
        alerts.append("The active regulation was resolved with low confidence; sources disagree.")
    if end and now > end:
        alerts.append(f"The stored regulation window ended {window.get('end')}; a new regulation is probably active.")
    age_days = None
    if snapshot is None:
        alerts.append("There is no meta snapshot for this regulation yet.")
    else:
        generated = _parse(snapshot.get("generated_at"))
        age_days = round((now - generated).total_seconds() / 86400, 1) if generated else None
        if age_days is not None and age_days > max_age_days:
            alerts.append(f"The meta snapshot is {age_days:g} days old (limit {max_age_days}).")
        if snapshot.get("early_meta"):
            alerts.append("Early meta: " + "; ".join(snapshot.get("early_meta_reasons") or []))
    upcoming = regulation.get("next_regulation")
    return {
        "regulation_id": regulation["regulation_id"],
        "label": regulation.get("label"),
        "game": regulation.get("game"),
        "active_window": window,
        "mechanics": regulation.get("mechanics", []),
        "rules": regulation.get("rules", {}),
        "official_url": regulation.get("official_url"),
        "confidence": regulation.get("confidence"),
        "regulation_checked_at": regulation.get("checked_at"),
        "next_regulation": upcoming,
        "snapshot_generated_at": snapshot.get("generated_at") if snapshot else None,
        "snapshot_age_days": age_days,
        "data_through": snapshot.get("data_through") if snapshot else None,
        "early_meta": bool(snapshot and snapshot.get("early_meta")),
        "segments": snapshot.get("segments") if snapshot else None,
        "needs_refresh": bool(alerts),
        "alerts": alerts,
        "recommendation": (
            "Offer to run the refresh (vgc-refresh / python3 tools/vgc_refresh.py) before relying on these numbers."
            if alerts
            else "Data is current; no refresh needed."
        ),
    }


# -- name resolution -------------------------------------------------------------

def resolve_species(data: MetaData, name: str) -> tuple[str, str | None]:
    """Map user text ("Mega Charizard Y", "charizard-mega-y", "Basculegion-F") to (species, mega)."""
    snapshot = _require_snapshot(data)
    known = {row["species"]: row for row in snapshot["usage"]}
    megas = {row["mega"]: row for row in snapshot["megas"]}
    text = name.strip()
    mega_words = re.match(r"(?i)^mega\s+(.+?)(?:\s+([xyz]))?$", text)
    if mega_words:
        text = f"{mega_words.group(1)}-mega" + (f"-{mega_words.group(2)}" if mega_words.group(2) else "")
    key = slug(text)
    if key in megas:
        return data.pokedex.identity(key)
    if key in known:
        return key, None
    for row in snapshot["usage"]:
        if slug(row["name"]) == key:
            return row["species"], None
    for row in snapshot["megas"]:
        if slug(row["name"]) == key:
            return data.pokedex.identity(row["mega"])
    candidates = list(known) + list(megas)
    close = difflib.get_close_matches(key, candidates, n=3, cutoff=0.75)
    if len(close) == 1 or (close and difflib.SequenceMatcher(None, key, close[0]).ratio() > 0.9):
        return data.pokedex.identity(close[0])
    hint = f" Did you mean: {', '.join(close)}?" if close else ""
    raise QueryError(f"'{name}' does not appear in the current snapshot.{hint}")


# -- queries --------------------------------------------------------------------

def usage(data: MetaData, *, segment: str = "in_person", top: int = 20) -> list[dict[str, Any]]:
    snapshot = _require_snapshot(data)
    rows = [row for row in snapshot["usage"] if row[segment]["teams"]]
    rows.sort(key=lambda row: -(row[segment]["share"] or 0))
    return rows[:top]


def pokemon(data: MetaData, name: str) -> dict[str, Any]:
    snapshot = _require_snapshot(data)
    species, mega = resolve_species(data, name)
    row = next((item for item in snapshot["usage"] if item["species"] == species), None)
    if row is None:
        raise QueryError(f"No usage row for {species}")
    sets = next((item for item in snapshot["sets"] if item["species"] == species), None)
    pairs = {
        segment: [item for item in snapshot["pairs"][segment] if species in item["species"]][:8]
        for segment in SEGMENTS
    }
    matchups = snapshot["matchups"]["pairs"]
    as_attacker = sorted(
        (item for item in matchups if item["species"] == species), key=lambda item: -item["win_rate"]
    )
    top_cut = [team for team in snapshot["top_cut_teams"] if any(mon["species"] == species for mon in team["team"])]
    return {
        "species": species,
        "name": row["name"],
        "mega_asked": mega,
        "usage": {segment: row[segment] for segment in SEGMENTS},
        "megas": [item for item in snapshot["megas"] if data.pokedex.identity(item["mega"])[0] == species],
        "sets": sets,
        "pairs": pairs,
        "best_matchups": as_attacker[:5],
        "worst_matchups": list(reversed(as_attacker[-5:])),
        "top_cut_appearances": len(top_cut),
        "recent_top_cut": top_cut[:5],
    }


def matchup(data: MetaData, first: str, second: str) -> dict[str, Any]:
    snapshot = _require_snapshot(data)
    a, _ = resolve_species(data, first)
    b, _ = resolve_species(data, second)
    found = [item for item in snapshot["matchups"]["pairs"] if (item["species"], item["opponent"]) in {(a, b), (b, a)}]
    return {"species": a, "opponent": b, "basis": snapshot["matchups"]["basis"], "records": found}


def top_cut(data: MetaData, *, segment: str | None = None, species: str | None = None, limit: int = 16) -> list[dict[str, Any]]:
    snapshot = _require_snapshot(data)
    wanted = resolve_species(data, species)[0] if species else None
    rows = [
        team
        for team in snapshot["top_cut_teams"]
        if (segment is None or team["segment"] == segment)
        and (wanted is None or any(mon["species"] == wanted for mon in team["team"]))
    ]
    return rows[:limit]


def events(data: MetaData) -> list[dict[str, Any]]:
    return _require_snapshot(data)["events"]


# -- team analysis ----------------------------------------------------------------

_SHOWDOWN_HEADER = re.compile(r"^(?P<name>[^@(]+?)(?:\s*\((?P<real>[^)]+)\))?(?:\s*\([MF]\))?\s*(?:@\s*(?P<item>.+))?$")


def parse_team(text: str) -> list[dict[str, Any]]:
    """Parse a Showdown export or one-line-per-mon 'Name @ Item | Ability | Nature | Move, Move' text."""
    mons: list[dict[str, Any]] = []
    lines = [line.strip() for line in text.replace("\r", "").split("\n")]
    if any("|" in line for line in lines):
        for line in lines:
            if not line or "|" not in line:
                continue
            parts = [part.strip() for part in line.split("|")]
            head = _SHOWDOWN_HEADER.match(parts[0])
            name = (head.group("real") or head.group("name")).strip() if head else parts[0]
            mons.append(
                {
                    "name": name,
                    "item": (head.group("item") or "").strip() or None if head else None,
                    "ability": parts[1] if len(parts) > 1 else None,
                    "nature": parts[2] if len(parts) > 2 else None,
                    "moves": [move.strip() for move in ",".join(parts[3:]).split(",") if move.strip()],
                }
            )
        return mons
    current: dict[str, Any] | None = None
    for line in lines + [""]:
        if not line:
            if current:
                mons.append(current)
            current = None
            continue
        if current is None:
            head = _SHOWDOWN_HEADER.match(line)
            name = (head.group("real") or head.group("name")).strip() if head else line
            current = {"name": name, "item": (head.group("item") or "").strip() or None if head else None,
                       "ability": None, "nature": None, "moves": []}
        elif line.lower().startswith("ability:"):
            current["ability"] = line.split(":", 1)[1].strip()
        elif line.lower().endswith(" nature"):
            current["nature"] = line[: -len(" nature")].strip()
        elif line.startswith("-"):
            current["moves"].append(line.lstrip("- ").strip())
    return mons


def team(data: MetaData, text: str) -> dict[str, Any]:
    snapshot = _require_snapshot(data)
    parsed = parse_team(text)
    if not parsed:
        raise QueryError("could not read any Pokémon from the team text")
    usage_by = {row["species"]: row for row in snapshot["usage"]}
    sets_by = {row["species"]: row for row in snapshot["sets"]}
    members = []
    for mon in parsed:
        try:
            species, _ = resolve_species(data, mon["name"])
        except QueryError as exc:
            members.append({"input": mon, "error": str(exc)})
            continue
        mega = data.pokedex.mega_for(species, mon.get("item"))
        row = usage_by.get(species)
        set_row = sets_by.get(species)
        notes = []
        if set_row:
            common_moves = {slug(move["name"]) for move in set_row["moves"]}
            uncommon = [move for move in mon["moves"] if slug(move) not in common_moves]
            if uncommon:
                notes.append("uncommon moves (outside the top 10 for this species): " + ", ".join(uncommon))
            items = [item["name"] for item in set_row["items"]]
            if mon.get("item") and slug(mon["item"]) not in {slug(item) for item in items}:
                notes.append(f"item {mon['item']} is outside the top {len(items)} items for this species")
        members.append(
            {
                "input": mon,
                "species": species,
                "name": data.pokedex.display(species),
                "mega": mega,
                "usage": {segment: row[segment] for segment in SEGMENTS} if row else None,
                "common_set": set_row["top_sets"][0] if set_row and set_row["top_sets"] else None,
                "notes": notes,
            }
        )
    roster = [member["species"] for member in members if "species" in member]
    cores = {
        segment: [
            combo
            for combo in snapshot["pairs"][segment] + snapshot["trios"][segment]
            if set(combo["species"]) <= set(roster)
        ]
        for segment in ("in_person", "total")
    }
    matchups = snapshot["matchups"]["pairs"]
    threats = []
    for row in snapshot["matchups"]["species"]:
        opponent = row["species"]
        if opponent in roster:
            continue
        records = [item for item in matchups if item["species"] == opponent and item["opponent"] in roster]
        if not records:
            continue
        wins = sum(item["wins"] for item in records)
        games = sum(item["games"] for item in records)
        threats.append(
            {
                "species": opponent,
                "name": row["name"],
                "win_rate_vs_team": round(wins / games, 4),
                "games": games,
                "vs": sorted(((item["opponent"], item["win_rate"]) for item in records), key=lambda pair: -pair[1]),
            }
        )
    threats.sort(key=lambda item: -item["win_rate_vs_team"])
    return {
        "members": members,
        "cores_seen_in_meta": cores,
        "threats": threats[:8],
        "favourable": list(reversed(threats[-5:])),
        "basis": snapshot["matchups"]["basis"],
    }


# -- refresh diff ---------------------------------------------------------------

def diff_snapshots(old: dict[str, Any] | None, new: dict[str, Any], *, threshold: float = 0.02, limit: int = 8) -> dict[str, Any]:
    """Summarize what changed between two snapshots of the same regulation."""
    if not old or old["regulation"]["regulation_id"] != new["regulation"]["regulation_id"]:
        return {
            "comparable": False,
            "new_events": new["events"],
            "movers": {},
        }
    old_events = {event["key"] for event in old["events"]}
    old_usage = {row["species"]: row for row in old["usage"]}
    movers: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for segment in ("in_person", "online"):
        changes = []
        for row in new["usage"]:
            now_share = row[segment]["share"] or 0
            before = old_usage.get(row["species"], {}).get(segment, {}).get("share") or 0
            if abs(now_share - before) >= threshold:
                changes.append({"species": row["species"], "name": row["name"], "before": before, "after": now_share,
                                "delta": round(now_share - before, 4)})
        changes.sort(key=lambda item: -item["delta"])
        movers[segment] = {
            "up": [item for item in changes if item["delta"] > 0][:limit],
            "down": list(reversed([item for item in changes if item["delta"] < 0]))[:limit],
        }
    old_top_cut = {(team["event_key"], team["placement"]) for team in old["top_cut_teams"]}
    return {
        "comparable": True,
        "new_events": [event for event in new["events"] if event["key"] not in old_events],
        "removed_events": sorted(old_events - {event["key"] for event in new["events"]}),
        "movers": movers,
        "new_top_cut_teams": [
            team for team in new["top_cut_teams"]
            if team["segment"] == "in_person" and (team["event_key"], team["placement"]) not in old_top_cut
        ],
        "segments_before": old["segments"],
        "segments_after": new["segments"],
    }
