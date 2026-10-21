"""Aggregate normalized events into the meta snapshot.

Segments
--------
* ``in_person``: official events. Usage share and win rate use only events
  with the whole field's team lists; day 2 figures use every event with day 2
  information (including day-2-only fallback events); top cut uses all.
* ``online``: Limitless tournaments inside the online window.
* ``total``: whole-field in-person teams plus online teams.

``by_event`` repeats usage, Megas and the top teams for each event, in-person
and online (day-2-only fallback events are labeled ``basis: day2_only``), and
``trend`` compares the
most recent whole-field in-person events with the earlier ones.

Win rates are wins / (wins + losses) over the teams' full records (ties are
ignored). Matchups are team-sheet level: they count which species were on
each team in a match, not which ones were brought.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from itertools import combinations
from typing import Any, Iterable

from .events import IN_PERSON, ONLINE, Event, Team
from .pokedex import Pokedex, name_key
from .text import iso_z


SCHEMA_VERSION = "meta-snapshot-v2"


@dataclass
class _Tally:
    teams: int = 0
    wins: int = 0
    losses: int = 0

    def add(self, team: Team) -> None:
        self.teams += 1
        if team.has_record:
            self.wins += team.wins or 0
            self.losses += team.losses or 0

    def summary(self, denominator: int) -> dict[str, Any]:
        games = self.wins + self.losses
        return {
            "teams": self.teams,
            "share": _ratio(self.teams, denominator),
            "win_rate": _ratio(self.wins, games),
            "games": games,
        }


@dataclass
class _Segment:
    teams: int = 0
    species: dict[str, _Tally] = field(default_factory=lambda: defaultdict(_Tally))
    megas: dict[str, _Tally] = field(default_factory=lambda: defaultdict(_Tally))
    pairs: dict[tuple[str, ...], _Tally] = field(default_factory=lambda: defaultdict(_Tally))
    trios: dict[tuple[str, ...], _Tally] = field(default_factory=lambda: defaultdict(_Tally))

    def add(self, team: Team) -> None:
        self.teams += 1
        species = sorted({mon.species for mon in team.mons})
        for name in species:
            self.species[name].add(team)
        for mega in {mon.mega for mon in team.mons if mon.mega}:
            self.megas[mega].add(team)
        for pair in combinations(species, 2):
            self.pairs[pair].add(team)
        for trio in combinations(species, 3):
            self.trios[trio].add(team)


def build_snapshot(
    events: Iterable[Event],
    *,
    regulation: dict[str, Any],
    pokedex: Pokedex,
    config: dict[str, Any],
    now: datetime,
    sources: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    settings = config["pipeline"]["aggregation"]
    events = sorted(events, key=lambda event: (event.date, event.key))
    in_person = [event for event in events if event.segment == IN_PERSON]
    online = [event for event in events if event.segment == ONLINE]
    full_field = [event for event in in_person if event.coverage.get("full_field")]

    segments = {"in_person": _Segment(), "online": _Segment(), "total": _Segment()}
    day2 = _Segment()
    # Whole-field events with day 2 information: teams entered / teams that made day 2.
    entered: Counter[str] = Counter()
    converted: Counter[str] = Counter()
    top_cut: Counter[str] = Counter()
    top_cut_size = int(settings["in_person_top_cut"])

    for event in full_field:
        for team in event.teams:
            segments["in_person"].add(team)
            segments["total"].add(team)
            if event.coverage.get("day2") and team.day2 is not None:
                for species in {mon.species for mon in team.mons}:
                    entered[species] += 1
                    converted[species] += int(team.day2)
    for event in in_person:
        for team in event.teams:
            if team.day2:
                day2.add(team)
            if team.placement is not None and team.placement <= top_cut_size:
                for species in {mon.species for mon in team.mons}:
                    top_cut[species] += 1
    for event in online:
        for team in event.teams:
            segments["online"].add(team)
            segments["total"].add(team)

    ranking = "in_person" if segments["in_person"].teams >= int(settings["min_teams_to_rank_in_person"]) else "total"
    usage = _usage(segments, day2, entered, converted, top_cut, pokedex, ranking)

    early_reasons = []
    if len(in_person) < int(settings["early_meta_min_in_person_events"]):
        early_reasons.append(
            f"only {len(in_person)} in-person event(s); at least "
            f"{settings['early_meta_min_in_person_events']} are needed for a settled read"
        )
    if segments["total"].teams < int(settings["early_meta_min_total_teams"]):
        early_reasons.append(
            f"only {segments['total'].teams} teams in total; at least "
            f"{settings['early_meta_min_total_teams']} are needed"
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": iso_z(now),
        "regulation": {
            key: regulation.get(key)
            for key in ("regulation_id", "label", "game", "active_window", "confidence", "stale", "checked_at")
        },
        "early_meta": bool(early_reasons),
        "early_meta_reasons": early_reasons,
        "data_through": events[-1].date if events else None,
        "online_window_days": int(config["pipeline"]["online_window_days"]),
        "ranked_by": ranking,
        "segments": {
            "in_person": {
                "events": len(in_person),
                "full_field_events": len(full_field),
                "teams": segments["in_person"].teams,
                "day2_teams": day2.teams,
            },
            "online": {"events": len(online), "teams": segments["online"].teams},
            "total": {"events": len(full_field) + len(online), "teams": segments["total"].teams},
        },
        "usage": usage,
        "megas": _megas(segments, pokedex, ranking),
        "pairs": {
            name: _combos(segment.pairs, segment.teams, pokedex, int(settings["top_pairs"]), int(settings["min_combo_teams"]))
            for name, segment in segments.items()
        },
        "trios": {
            name: _combos(segment.trios, segment.teams, pokedex, int(settings["top_trios"]), int(settings["min_combo_teams"]))
            for name, segment in segments.items()
        },
        "sets": _sets(events, usage, pokedex, settings),
        "matchups": _matchups(full_field, usage, pokedex, settings),
        "top_cut_teams": _top_cut_teams(in_person, online, pokedex, settings),
        "events": [_event_summary(event) for event in events],
        "by_event": _by_event(in_person + online, pokedex, settings),
        "trend": _trend(full_field, pokedex, settings),
        "sources": sources,
        "warnings": warnings,
    }


# -- sections ----------------------------------------------------------------

def _usage(
    segments: dict[str, _Segment],
    day2: _Segment,
    entered: Counter[str],
    converted: Counter[str],
    top_cut: Counter[str],
    dex: Pokedex,
    ranking: str,
) -> list[dict[str, Any]]:
    rows = []
    for species in set(segments["total"].species) | set(day2.species):
        in_person = segments["in_person"].species.get(species, _Tally()).summary(segments["in_person"].teams)
        day2_teams = day2.species.get(species, _Tally()).teams
        in_person.update(
            day2_teams=day2_teams,
            day2_share=_ratio(day2_teams, day2.teams),
            day2_conversion=_ratio(converted.get(species, 0), entered.get(species, 0)),
            top_cut_teams=top_cut.get(species, 0),
        )
        rows.append(
            {
                "species": species,
                "name": dex.display(species),
                "total": segments["total"].species.get(species, _Tally()).summary(segments["total"].teams),
                "in_person": in_person,
                "online": segments["online"].species.get(species, _Tally()).summary(segments["online"].teams),
            }
        )
    return sorted(
        rows,
        key=lambda row: (-(row[ranking]["share"] or 0), -(row["total"]["share"] or 0), row["species"]),
    )


def _megas(segments: dict[str, _Segment], dex: Pokedex, ranking: str) -> list[dict[str, Any]]:
    rows = []
    for mega in set(segments["total"].megas):
        rows.append(
            {
                "mega": mega,
                "name": dex.display(mega),
                **{
                    name: segment.megas.get(mega, _Tally()).summary(segment.teams)
                    for name, segment in segments.items()
                },
            }
        )
    return sorted(rows, key=lambda row: (-(row[ranking]["share"] or 0), row["mega"]))


def _combos(
    tallies: dict[tuple[str, ...], _Tally], denominator: int, dex: Pokedex, limit: int, minimum: int
) -> list[dict[str, Any]]:
    ranked = sorted(
        ((combo, tally) for combo, tally in tallies.items() if tally.teams >= minimum),
        key=lambda item: (-item[1].teams, item[0]),
    )[:limit]
    return [
        {"species": list(combo), "names": [dex.display(name) for name in combo], **tally.summary(denominator)}
        for combo, tally in ranked
    ]


def _sets(
    events: list[Event], usage: list[dict[str, Any]], dex: Pokedex, settings: dict[str, Any]
) -> list[dict[str, Any]]:
    wanted = [row["species"] for row in usage[: int(settings["sets_top_species"])]]
    collected: dict[str, dict[str, Any]] = {
        species: {
            "sample": 0,
            "in_person_sample": 0,
            "items": Counter(),
            "abilities": Counter(),
            "natures": Counter(),
            "moves": Counter(),
            "megas": Counter(),
            "spreads": Counter(),
            "display": defaultdict(Counter),
        }
        for species in wanted
    }
    for event in events:
        for team in event.teams:
            for mon in team.mons:
                bucket = collected.get(mon.species)
                if bucket is None or not mon.has_set:
                    continue
                bucket["sample"] += 1
                if event.segment == IN_PERSON:
                    bucket["in_person_sample"] += 1
                for label, value in (("items", mon.item), ("abilities", mon.ability), ("natures", mon.nature)):
                    key = name_key(value)
                    if key:
                        bucket[label][key] += 1
                        bucket["display"][key][value] += 1
                moves = sorted({name_key(move) for move in mon.moves if name_key(move)})
                for move_name in mon.moves:
                    key = name_key(move_name)
                    if key:
                        bucket["display"][key][move_name] += 1
                for key in moves:
                    bucket["moves"][key] += 1
                if mon.mega:
                    bucket["megas"][mon.mega] += 1
                bucket["spreads"][(name_key(mon.item), name_key(mon.ability), name_key(mon.nature), tuple(moves))] += 1

    result = []
    for species in wanted:
        bucket = collected[species]
        sample = bucket["sample"]
        if not sample:
            continue
        display = {key: counter.most_common(1)[0][0] for key, counter in bucket["display"].items()}

        def top(counter: Counter[str], limit: int) -> list[dict[str, Any]]:
            return [
                {"name": display.get(key, key), "count": count, "share": _ratio(count, sample)}
                for key, count in counter.most_common(limit)
            ]

        result.append(
            {
                "species": species,
                "name": dex.display(species),
                "sample": sample,
                "in_person_sample": bucket["in_person_sample"],
                "items": top(bucket["items"], 6),
                "abilities": top(bucket["abilities"], 3),
                "natures": top(bucket["natures"], 4),
                "moves": top(bucket["moves"], 10),
                "megas": [
                    {"mega": mega, "name": dex.display(mega), "count": count, "share": _ratio(count, sample)}
                    for mega, count in bucket["megas"].most_common()
                ],
                "top_sets": [
                    {
                        "item": display.get(item, item),
                        "ability": display.get(ability, ability),
                        "nature": display.get(nature, nature),
                        "moves": [display.get(move, move) for move in moves],
                        "count": count,
                        "share": _ratio(count, sample),
                    }
                    for (item, ability, nature, moves), count in bucket["spreads"].most_common(5)
                ],
            }
        )
    return result


def _matchups(
    events: list[Event], usage: list[dict[str, Any]], dex: Pokedex, settings: dict[str, Any]
) -> dict[str, Any]:
    species = [row["species"] for row in usage if row["in_person"]["teams"]][: int(settings["matchup_species"])]
    wanted = set(species)
    tallies: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    matches = 0
    for event in events:
        for a_index, b_index, winner in event.matches:
            if winner < 0:
                continue
            matches += 1
            team_a = {mon.species for mon in event.teams[a_index].mons} & wanted
            team_b = {mon.species for mon in event.teams[b_index].mons} & wanted
            for mine, theirs, won in ((team_a, team_b, winner == a_index), (team_b, team_a, winner == b_index)):
                for x in mine:
                    for y in theirs:
                        if x != y:
                            tallies[(x, y)][0] += int(won)
                            tallies[(x, y)][1] += 1
    minimum = int(settings["matchup_min_games"])
    return {
        "basis": "team sheets (species on each team, not species brought to the game)",
        "matches": matches,
        "species": [{"species": name, "name": dex.display(name)} for name in species],
        "pairs": [
            {
                "species": x,
                "opponent": y,
                "wins": wins,
                "games": games,
                "win_rate": _ratio(wins, games),
            }
            for (x, y), (wins, games) in sorted(tallies.items())
            if games >= minimum
        ],
    }


def _top_cut_teams(
    in_person: list[Event], online: list[Event], dex: Pokedex, settings: dict[str, Any]
) -> list[dict[str, Any]]:
    rows = []
    for events, size in ((in_person, int(settings["in_person_top_cut"])), (online, int(settings["online_top_cut"]))):
        for event in sorted(events, key=lambda item: item.date, reverse=True):
            for team in sorted(event.teams, key=lambda item: item.placement or 10**6):
                if team.placement is None or team.placement > size:
                    continue
                rows.append(
                    {"event_key": event.key, "event": event.name, "date": event.date, "segment": event.segment, **_team_row(team, dex)}
                )
    limit = int(settings["max_top_cut_teams"])
    in_person_rows = [row for row in rows if row["segment"] == IN_PERSON]
    online_rows = [row for row in rows if row["segment"] == ONLINE]
    return in_person_rows + online_rows[: max(0, limit - len(in_person_rows))]


def _team_row(team: Team, dex: Pokedex) -> dict[str, Any]:
    return {
        "placement": team.placement,
        "player": team.name,
        "country": team.country,
        "record": _record(team),
        "team": [
            {
                "species": mon.species,
                "name": dex.display(mon.species),
                "mega": dex.display(mon.mega),
                "item": mon.item,
                "ability": mon.ability,
                "nature": mon.nature,
                "moves": mon.moves,
            }
            for mon in team.mons
        ],
    }


def _by_event(events: list[Event], dex: Pokedex, settings: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for event in sorted(events, key=lambda item: (item.date, item.key), reverse=True):
        online = event.segment == ONLINE
        top_cut_size = int(settings["online_top_cut" if online else "in_person_top_cut"])
        limit = int(settings["event_usage_top_online" if online else "event_usage_top"])
        full_field = bool(event.coverage.get("full_field"))
        species: dict[str, _Tally] = defaultdict(_Tally)
        megas: dict[str, _Tally] = defaultdict(_Tally)
        entered: Counter[str] = Counter()
        converted: Counter[str] = Counter()
        top_cut: Counter[str] = Counter()
        day2_teams = 0
        for team in event.teams:
            names = {mon.species for mon in team.mons}
            for name in names:
                species[name].add(team)
            for mega in {mon.mega for mon in team.mons if mon.mega}:
                megas[mega].add(team)
            day2_teams += int(bool(team.day2))
            if full_field and event.coverage.get("day2") and team.day2 is not None:
                for name in names:
                    entered[name] += 1
                    converted[name] += int(team.day2)
            if team.placement is not None and team.placement <= top_cut_size:
                for name in names:
                    top_cut[name] += 1
        teams = len(event.teams)
        ranked = sorted(species.items(), key=lambda item: (-item[1].teams, item[0]))[:limit]
        rows.append(
            {
                "key": event.key,
                "name": event.name,
                "date": event.date,
                "segment": event.segment,
                "players": event.players,
                "url": event.url,
                "basis": "full_field" if full_field else "day2_only",
                "teams": teams,
                "day2_teams": day2_teams,
                "usage": [
                    {
                        "species": name,
                        "name": dex.display(name),
                        **tally.summary(teams),
                        "day2_conversion": _ratio(converted.get(name, 0), entered.get(name, 0)),
                        "top_cut_teams": top_cut.get(name, 0),
                    }
                    for name, tally in ranked
                ],
                "megas": [
                    {"mega": mega, "name": dex.display(mega), **tally.summary(teams)}
                    for mega, tally in sorted(megas.items(), key=lambda item: (-item[1].teams, item[0]))[: limit // 2 if online else None]
                ],
                "top_teams": [
                    _team_row(team, dex)
                    for team in sorted(event.teams, key=lambda item: item.placement or 10**6)
                    if team.placement is not None and team.placement <= top_cut_size
                ],
            }
        )
    return rows


def _trend(full_field: list[Event], dex: Pokedex, settings: dict[str, Any]) -> dict[str, Any]:
    recent_count = int(settings["trend_recent_events"])
    ordered = sorted(full_field, key=lambda item: (item.date, item.key))
    recent, earlier = ordered[-recent_count:], ordered[:-recent_count]
    result: dict[str, Any] = {
        "available": bool(earlier),
        "basis": "whole-field in-person events",
        "recent_events": [{"key": event.key, "name": event.name, "date": event.date} for event in recent],
        "earlier_events": [{"key": event.key, "name": event.name, "date": event.date} for event in earlier],
        "recent_teams": sum(len(event.teams) for event in recent),
        "earlier_teams": sum(len(event.teams) for event in earlier),
        "species": [],
        "megas": [],
    }
    if not earlier:
        return result
    minimum = float(settings["trend_min_share"])
    pickers = {
        "species": lambda team: {mon.species for mon in team.mons},
        "megas": lambda team: {mon.mega for mon in team.mons if mon.mega},
    }
    for label, pick in pickers.items():
        groups = []
        for events in (recent, earlier):
            tallies: dict[str, _Tally] = defaultdict(_Tally)
            for event in events:
                for team in event.teams:
                    for name in pick(team):
                        tallies[name].add(team)
            groups.append(tallies)
        rows = []
        for name in set(groups[0]) | set(groups[1]):
            latest = groups[0].get(name, _Tally()).summary(result["recent_teams"])
            before = groups[1].get(name, _Tally()).summary(result["earlier_teams"])
            if max(latest["share"] or 0, before["share"] or 0) < minimum:
                continue
            rows.append(
                {
                    "id": name,
                    "name": dex.display(name),
                    "recent": latest,
                    "earlier": before,
                    "share_delta": round((latest["share"] or 0) - (before["share"] or 0), 4),
                }
            )
        result[label] = sorted(rows, key=lambda row: (-row["share_delta"], row["id"]))
    return result


def _event_summary(event: Event) -> dict[str, Any]:
    return {
        "key": event.key,
        "source": event.source,
        "name": event.name,
        "date": event.date,
        "segment": event.segment,
        "tier": event.tier,
        "players": event.players,
        "url": event.url,
        "coverage": event.coverage,
    }


def _record(team: Team) -> str | None:
    if not team.has_record:
        return None
    return f"{team.wins}-{team.losses}" + (f"-{team.ties}" if team.ties else "")


def _ratio(numerator: int, denominator: int) -> float | None:
    if not denominator:
        return None
    return round(numerator / denominator, 4)
