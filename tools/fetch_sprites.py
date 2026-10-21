#!/usr/bin/env python3
"""Download the Pokemon sprites the coach page shows into a local cache.

Added in the estebanmoreno04 fork of NoahJenkins/vgc-coach. The page cannot
load images from other sites, so tools/build_coach_page.py embeds the cached
files. Sprites come from Pokemon Showdown (config ``coach_page.sprites``),
through the polite HTTP client (robots.txt, one request per second). Only
species and Megas present in data/current/snapshot.json are fetched, each
once; misses are remembered so later runs only ask for new names.

    python3 tools/fetch_sprites.py              # fetch what is missing
    python3 tools/fetch_sprites.py --retry-missing
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vgc_data.config import REPO_ROOT, load_config  # noqa: E402
from vgc_data.http import HTTPStatusError, PoliteClient, SourceError  # noqa: E402
from vgc_data.pokedex import slug  # noqa: E402


MANIFEST = "manifest.json"


def sprite_ids(snapshot: dict[str, Any]) -> list[str]:
    """Every species and Mega id the page can show."""
    ids: set[str] = {row["species"] for row in snapshot["usage"]} | {row["mega"] for row in snapshot["megas"]}
    for event in snapshot.get("by_event", []):
        ids.update(row["species"] for row in event["usage"])
        ids.update(row["mega"] for row in event["megas"])
        for team in event.get("top_teams", []):
            for mon in team["team"]:
                ids.add(mon["species"])
                if mon.get("mega"):
                    ids.add(slug(mon["mega"]))
    return sorted(ids)


def candidates(sprite_id: str) -> list[str]:
    """Showdown file names to try: 'charizard-mega-y' -> 'charizard-megay', 'kommo-o' -> 'kommoo'."""
    head, _, rest = sprite_id.partition("-")
    names = [sprite_id.replace("-", "")]
    if rest:
        names.insert(0, f"{head}-{rest.replace('-', '')}")
    names.append(sprite_id)
    return list(dict.fromkeys(names))


def fetch(client: PoliteClient, base_url: str, cache: Path, ids: Iterable[str], *, retry_missing: bool = False) -> dict[str, Any]:
    cache.mkdir(parents=True, exist_ok=True)
    manifest_path = cache / MANIFEST
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    for sprite_id in ids:
        known = manifest.get(sprite_id)
        if known and known.get("file") and (cache / known["file"]).exists():
            continue
        if known and not known.get("file") and not retry_missing:
            continue
        entry: dict[str, Any] = {"file": None, "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        for name in candidates(sprite_id):
            try:
                body = client.get_bytes(f"{base_url}{name}.png")
            except HTTPStatusError as exc:
                if exc.status == 404:
                    continue
                raise
            if not body.startswith(b"\x89PNG"):
                continue
            (cache / f"{sprite_id}.png").write_bytes(body)
            entry.update(file=f"{sprite_id}.png", source=f"{base_url}{name}.png")
            break
        manifest[sprite_id] = entry
        manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--retry-missing", action="store_true", help="Ask again for names that had no sprite.")
    args = parser.parse_args(argv)
    config = load_config()
    settings = config["coach_page"]["sprites"]
    snapshot = json.loads((REPO_ROOT / config["paths"]["current_dir"] / "snapshot.json").read_text(encoding="utf-8"))
    ids = sprite_ids(snapshot)
    try:
        manifest = fetch(
            PoliteClient.from_config(config, root=REPO_ROOT),
            settings["base_url"],
            REPO_ROOT / settings["cache_dir"],
            ids,
            retry_missing=args.retry_missing,
        )
    except SourceError as exc:
        print(f"fetch_sprites: {exc}", file=sys.stderr)
        return 1
    found = sum(1 for sprite_id in ids if (manifest.get(sprite_id) or {}).get("file"))
    missing = [sprite_id for sprite_id in ids if not (manifest.get(sprite_id) or {}).get("file")]
    print(f"{found}/{len(ids)} sprites cached in {settings['cache_dir']}")
    if missing:
        print("No sprite (Megas fall back to their base form): " + ", ".join(missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
