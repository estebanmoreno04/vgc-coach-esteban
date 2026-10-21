#!/usr/bin/env python3
"""Build data/current/snapshot.json for the regulation in data/current/regulation.json.

Downloads only events that were not processed before (see
data/current/processed_events.json), normalizes them and aggregates usage,
win rates, cores, sets, matchups and top cut teams. Official in-person events
come first (VGC History, with limitlessvgc.com as fallback); online
tournaments from the Limitless API complement them.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vgc_data.aggregate import build_snapshot  # noqa: E402
from vgc_data.config import DEFAULT_CONFIG_PATH, REPO_ROOT, load_config  # noqa: E402
from vgc_data.events import ONLINE, EventStore  # noqa: E402
from vgc_data.http import PoliteClient, SourceError, TextClient  # noqa: E402
from vgc_data.meta_sources import PipelineContext  # noqa: E402
from vgc_data.meta_sources import limitless_events, limitlessvgc_events, vgchistory_events  # noqa: E402
from vgc_data.pokedex import Pokedex, slug  # noqa: E402
from vgc_data.text import parse_iso_z, utc_now  # noqa: E402


SNAPSHOT_FILE = "snapshot.json"
POKEDEX_FILE = "pokedex.json"
FETCH_ERRORS = (SourceError, ValueError, KeyError, TypeError, IndexError)


class PipelineError(RuntimeError):
    """The pipeline cannot run (no regulation, mismatched data)."""


@dataclass
class SourceRun:
    source_id: str
    role: str
    url: str
    credit: str | None
    status: str = "ok"
    new_events: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "role": self.role,
            "url": self.url,
            "credit": self.credit,
            "status": self.status,
            "new_events": self.new_events,
            "skipped": self.skipped,
            "errors": self.errors,
        }


@dataclass
class PipelineResult:
    payload: dict[str, Any]
    runs: list[SourceRun]
    path: Path | None


def run(
    *,
    config: dict[str, Any],
    client: TextClient,
    now: datetime,
    root: Path = REPO_ROOT,
    dry_run: bool = False,
    offline: bool = False,
) -> PipelineResult:
    current_dir = root / config["paths"]["current_dir"]
    regulation_path = current_dir / "regulation.json"
    if not regulation_path.exists():
        raise PipelineError("data/current/regulation.json is missing; run tools/resolve_regulation.py first")
    regulation = json.loads(regulation_path.read_text(encoding="utf-8"))
    regulation_id = regulation["regulation_id"]

    store = EventStore(current_dir)
    if store.regulation_id and store.regulation_id != regulation_id:
        raise PipelineError(
            f"stored events belong to {store.regulation_id} but the active regulation is "
            f"{regulation_id}; run tools/resolve_regulation.py to archive them"
        )
    pokedex = Pokedex.load(current_dir / POKEDEX_FILE)
    ctx = PipelineContext(client, config, now, regulation, pokedex)
    if regulation.get("stale"):
        ctx.warnings.append("regulation.json is marked stale: the active regulation could not be re-checked.")
    if regulation.get("confidence") == "low":
        ctx.warnings.append("The active regulation was resolved with low confidence.")

    sources = config["pipeline"]["sources"]
    runs: list[SourceRun] = []
    known_events: list[tuple[date, str]] = _stored_in_person(store)

    if not (dry_run or offline):
        if sources["vgchistory"].get("enabled"):
            runs.append(_run_vgchistory(ctx, store, known_events))
        if sources["limitlessvgc"].get("enabled"):
            runs.append(_run_limitlessvgc(ctx, store, known_events))
        if sources["limitless_api"].get("enabled"):
            runs.append(_run_limitless(ctx, store))
        _prune_online(ctx, store)

    events = [event for event in store.load_all() if event.regulation_id == regulation_id]
    payload = build_snapshot(
        events,
        regulation=regulation,
        pokedex=pokedex,
        config=config,
        now=now,
        sources=[source_run.to_dict() for source_run in runs],
        warnings=ctx.warnings,
    )
    _validate(payload, root / config["paths"]["snapshot_schema"])
    if dry_run:
        return PipelineResult(payload, runs, None)
    store.write_index(regulation_id)
    pokedex.save(current_dir / POKEDEX_FILE)
    path = current_dir / SNAPSHOT_FILE
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return PipelineResult(payload, runs, path)


# -- sources -------------------------------------------------------------------

def _run_vgchistory(ctx: PipelineContext, store: EventStore, known: list[tuple[date, str]]) -> SourceRun:
    cfg = ctx.source("vgchistory")
    run = SourceRun("vgchistory", "in_person", cfg["base_url"], cfg.get("credit"))
    try:
        tournaments, registry = vgchistory_events.load_registry(ctx)
    except FETCH_ERRORS as exc:
        run.status = "error"
        run.errors.append(f"{type(exc).__name__}: {exc}")
        ctx.warnings.append("VGC History is unavailable; in-person data relies on stored events and the fallback.")
        return run
    ctx.pokedex.merge(registry)
    for entry in vgchistory_events.discover(ctx, tournaments):
        key = f"vgchistory:{entry['id']}"
        known.append(vgchistory_events.city_key(entry))
        if not _needs_fetch(ctx, store, key, entry["_date"]):
            continue
        try:
            event = vgchistory_events.fetch(ctx, entry)
        except FETCH_ERRORS as exc:
            store.mark(key, status="error", fetched_at=ctx.now, error=f"{type(exc).__name__}: {exc}")
            run.errors.append(f"{entry['id']}: {exc}")
            continue
        store.save(event)
        store.index[key]["city"] = vgchistory_events.city_key(entry)[1]
        run.new_events += 1
    return run


def _run_limitlessvgc(ctx: PipelineContext, store: EventStore, known: list[tuple[date, str]]) -> SourceRun:
    cfg = ctx.source("limitlessvgc")
    run = SourceRun("limitlessvgc", "in_person_fallback", cfg["base_url"], cfg.get("credit"))
    try:
        entries = limitlessvgc_events.discover(ctx)
    except FETCH_ERRORS as exc:
        run.status = "error"
        run.errors.append(f"{type(exc).__name__}: {exc}")
        return run
    for entry in entries:
        key = f"limitlessvgc:{entry['id']}"
        if limitlessvgc_events.matches_known_event(entry, known):
            if key in store.index:
                store.remove(key)  # the primary source now covers this event
            continue
        if not _needs_fetch(ctx, store, key, entry["_date"]):
            continue
        try:
            event = limitlessvgc_events.fetch(ctx, entry)
        except FETCH_ERRORS as exc:
            store.mark(key, status="error", fetched_at=ctx.now, error=f"{type(exc).__name__}: {exc}")
            run.errors.append(f"{entry['id']}: {exc}")
            continue
        store.save(event)
        run.new_events += 1
        ctx.warnings.append(
            f"{event.name} is only available from the limitlessvgc.com fallback (day 2 teams, no records)."
        )
    return run


def _run_limitless(ctx: PipelineContext, store: EventStore) -> SourceRun:
    cfg = ctx.source("limitless_api")
    run = SourceRun("limitless_api", "online", cfg["base_url"], cfg.get("credit"))
    try:
        key_format = limitless_events.format_key(ctx)
        if key_format is None:
            run.status = "error"
            run.errors.append(f"Limitless does not list a format for {ctx.regulation_id} yet.")
            return run
        entries = limitless_events.discover(ctx, key_format)
    except FETCH_ERRORS as exc:
        run.status = "error"
        run.errors.append(f"{type(exc).__name__}: {exc}")
        return run
    pending = [entry for entry in entries if f"limitless_api:{entry['id']}" not in store.index
               or store.index[f"limitless_api:{entry['id']}"].get("status") == "error"]
    budget = int(ctx.pipeline["max_new_online_events_per_run"])
    # Newest first, so a capped run keeps the freshest online data.
    for entry in sorted(pending, key=lambda item: item["_when"], reverse=True)[:budget]:
        key = f"limitless_api:{entry['id']}"
        try:
            event, reason = limitless_events.fetch(ctx, entry)
        except FETCH_ERRORS as exc:
            store.mark(key, status="error", fetched_at=ctx.now, error=f"{type(exc).__name__}: {exc}")
            run.errors.append(f"{entry['id']}: {exc}")
            continue
        if event is None:
            store.mark(key, status="skipped", fetched_at=ctx.now, reason=reason,
                       segment=ONLINE, date=entry["_when"].date().isoformat(), name=entry.get("name"))
            run.skipped += 1
            continue
        store.save(event)
        run.new_events += 1
    if len(pending) > budget:
        ctx.warnings.append(
            f"{len(pending) - budget} online events are pending and will be downloaded on the next run."
        )
    return run


# -- helpers --------------------------------------------------------------------

def _needs_fetch(ctx: PipelineContext, store: EventStore, key: str, event_date: date) -> bool:
    entry = store.index.get(key)
    if entry is None or entry.get("status") == "error":
        return True
    if entry.get("status") != "ok" or entry.get("complete"):
        return False
    recent = (ctx.now.date() - event_date).days <= int(ctx.pipeline["refetch_incomplete_days"])
    fetched_at = parse_iso_z(entry.get("fetched_at"))
    return recent and (fetched_at is None or ctx.now - fetched_at >= timedelta(hours=20))


def _stored_in_person(store: EventStore) -> list[tuple[date, str]]:
    known = []
    for key, entry in store.index.items():
        if key.startswith("vgchistory:") and entry.get("status") == "ok" and entry.get("date"):
            known.append((date.fromisoformat(entry["date"]), entry.get("city") or slug(entry.get("name", ""))))
    return known


def _prune_online(ctx: PipelineContext, store: EventStore) -> None:
    cutoff = (ctx.now - timedelta(days=int(ctx.pipeline["online_window_days"]))).date().isoformat()
    for key, entry in list(store.index.items()):
        if entry.get("segment") == ONLINE and entry.get("date", "9999") < cutoff:
            store.remove(key)


def _validate(payload: dict[str, Any], schema_path: Path) -> None:
    import jsonschema

    jsonschema.validate(payload, json.loads(schema_path.read_text(encoding="utf-8")))


def summarize(result: PipelineResult) -> str:
    payload = result.payload
    segments = payload["segments"]
    lines = [
        f"Snapshot for {payload['regulation']['regulation_id']} generated {payload['generated_at']}"
        + (f" -> {result.path.as_posix()}" if result.path else " (dry run)"),
        f"  in-person: {segments['in_person']['events']} events, {segments['in_person']['teams']} whole-field teams, "
        f"{segments['in_person']['day2_teams']} day 2 teams",
        f"  online: {segments['online']['events']} events, {segments['online']['teams']} teams "
        f"(last {payload['online_window_days']} days)",
        f"  data through: {payload['data_through']}  early meta: {payload['early_meta']}",
    ]
    for source_run in result.runs:
        lines.append(
            f"  - {source_run.source_id}: {source_run.status}, {source_run.new_events} new, "
            f"{source_run.skipped} skipped" + (f", {len(source_run.errors)} errors" if source_run.errors else "")
        )
        lines.extend(f"      ! {error}" for error in source_run.errors[:5])
    ranked = payload["ranked_by"]
    lines.append(f"  top usage ({ranked}):")
    for row in payload["usage"][:10]:
        stats = row[ranked]
        lines.append(
            f"    {row['name']:<22} {100 * (stats['share'] or 0):5.1f}%  WR "
            + (f"{100 * stats['win_rate']:4.1f}%" if stats["win_rate"] is not None else "  n/a")
        )
    for reason in payload["early_meta_reasons"]:
        lines.append(f"  ~ early meta: {reason}")
    for warning in payload["warnings"]:
        lines.append(f"  ! {warning}")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--now", help="Override the current time (ISO-8601 UTC).")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Re-aggregate the stored events without downloading or writing anything.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Re-aggregate the stored events and write the snapshot without downloading.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    now = parse_iso_z(args.now) if args.now else utc_now()
    client = PoliteClient.from_config(config, root=REPO_ROOT)
    try:
        result = run(config=config, client=client, now=now, dry_run=args.dry_run, offline=args.offline)
    except PipelineError as exc:
        print(f"Cannot build the snapshot: {exc}", file=sys.stderr)
        return 2
    print(summarize(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
