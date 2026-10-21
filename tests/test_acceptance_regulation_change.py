"""Acceptance test: the whole system follows a regulation change by itself.

Starting from a repository state on the old regulation, every source starts
saying that a new regulation (the fictional "M-D" of the fixtures) is active.
One refresh, with no code or configuration change, must:

* detect the new regulation from the official window and community sources;
* archive the old regulation's data and stop using it;
* build a new snapshot from the new regulation's tournaments only;
* make every query, the freshness check and the weekly issue follow along.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
sys.path.insert(0, str(REPO_ROOT / "tools"))
sys.path.insert(0, str(REPO_ROOT / "tests"))

import meta_query  # noqa: E402
import run_weekly  # noqa: E402
import vgc_refresh  # noqa: E402
from test_build_snapshot import CLI as BUILD, CONFIG, NOW as OLD_NOW, FixtureClient as OldRegulationClient  # noqa: E402
from vgc_data import query  # noqa: E402
from vgc_data.http import HTTPStatusError, SourceError  # noqa: E402


NEW_NOW = datetime(2026, 12, 10, 12, 0, tzinfo=timezone.utc)
OFFICIAL = CONFIG["sources"]["official_news"]["base_url"]
VGCH = CONFIG["pipeline"]["sources"]["vgchistory"]["base_url"]
LIMITLESS = CONFIG["pipeline"]["sources"]["limitless_api"]["base_url"]
LVGC = CONFIG["pipeline"]["sources"]["limitlessvgc"]["base_url"]


def load_freshness():
    spec = importlib.util.spec_from_file_location("check_format_freshness", REPO_ROOT / "tools" / "check_format_freshness.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class NewRegulationClient:
    """Every source now describes the new regulation."""

    ROUTES = {
        OFFICIAL + "json/list.json": "regulation/official/list_with_md.json",
        OFFICIAL + "page/901.html": "regulation/official/page_901.html",
        VGCH + "data.js": "regulation/vgchistory/data_md.js",
        VGCH + "standings/regional-fixture-town-2027.json": "acceptance/standings_town.json",
        VGCH + "sheets/regional-fixture-town-2027.json": "acceptance/sheets_town.json",
        LIMITLESS + "games": "regulation/limitless/games.json",
        CONFIG["sources"]["victory_road"]["url"]: "regulation/victory_road/page_with_md.html",
        CONFIG["sources"]["pikalytics"]["url"]: "regulation/pikalytics/pokedex_md.md",
        LVGC + "tournaments": "acceptance/limitlessvgc_tournaments.html",
    }

    def __init__(self) -> None:
        self.requested: list[str] = []

    def get_text(self, url: str, *, ttl_hours: float = 0) -> str:
        self.requested.append(url)
        if url in self.ROUTES:
            return (FIXTURES / self.ROUTES[url]).read_text(encoding="utf-8")
        if url.startswith(LIMITLESS + "tournaments?"):
            name = "regulation/limitless/tournaments_md.json" if "page=1" in url else None
            return (FIXTURES / name).read_text(encoding="utf-8") if name else "[]"
        if re.match(rf"{re.escape(LIMITLESS)}tournaments/\w+/details$", url):
            return (FIXTURES / "acceptance/limitless_details.json").read_text(encoding="utf-8")
        if re.match(rf"{re.escape(LIMITLESS)}tournaments/\w+/standings$", url):
            return (FIXTURES / "acceptance/limitless_standings.json").read_text(encoding="utf-8")
        if url.startswith(VGCH):
            raise HTTPStatusError(url, 404)
        raise SourceError(f"{url}: not part of the scenario")


def tree_digest(*relative: str) -> str:
    digest = hashlib.sha256()
    for name in relative:
        base = REPO_ROOT / name
        files = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
        for path in files:
            digest.update(path.relative_to(REPO_ROOT).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


class RegulationChangeAcceptanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.config = copy.deepcopy(CONFIG)
        for key in ("regulation_schema", "snapshot_schema"):
            self.config["paths"][key] = str(REPO_ROOT / self.config["paths"][key])
        self.config["pipeline"]["aggregation"].update(min_teams_to_rank_in_person=1, min_combo_teams=1, matchup_min_games=1)
        self.current = self.root / "data/current"
        self.archive = self.root / "data/archive"
        self.current.mkdir(parents=True)
        (self.root / "data/schemas").mkdir(parents=True)
        shutil.copy(REPO_ROOT / "data/schemas/regulation-v1.schema.json", self.root / "data/schemas")
        # The repository as it was under the old regulation.
        shutil.copy(FIXTURES / "snapshot/regulation.json", self.current / "regulation.json")
        BUILD.run(config=self.config, client=OldRegulationClient(), now=OLD_NOW, root=self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_one_refresh_moves_everything_to_the_new_regulation(self) -> None:
        before = tree_digest("tools", "config", "skills")
        self.assertEqual(query.status(query.load(self.current), now=OLD_NOW)["regulation_id"], "M-C")

        summary = vgc_refresh.refresh(config=self.config, client=NewRegulationClient(), now=NEW_NOW, root=self.root)

        # 1. The new regulation is detected, with the official window.
        self.assertTrue(summary["regulation_changed"])
        self.assertEqual(summary["previous_regulation_id"], "M-C")
        regulation = json.loads((self.current / "regulation.json").read_text(encoding="utf-8"))
        self.assertEqual(regulation["regulation_id"], "M-D")
        self.assertEqual(regulation["confidence"], "high")
        self.assertEqual(regulation["active_window"]["start"], "2026-12-02T02:00:00Z")
        self.assertEqual(regulation["official_url"], OFFICIAL + "page/901.html")

        # 2. The old data is archived and refused for coaching.
        old = self.archive / "M-C"
        self.assertEqual(json.loads((old / "snapshot.json").read_text(encoding="utf-8"))["regulation"]["regulation_id"], "M-C")
        self.assertTrue((old / "events").is_dir())
        with self.assertRaises(query.QueryError):
            query.load(old)

        # 3. The new snapshot only holds the new regulation's tournaments.
        snapshot = json.loads((self.current / "snapshot.json").read_text(encoding="utf-8"))
        self.assertEqual(snapshot["regulation"]["regulation_id"], "M-D")
        keys = [event["key"] for event in snapshot["events"]]
        self.assertIn("vgchistory:regional-fixture-town-2027", keys)
        self.assertEqual(sum(key.startswith("limitless_api:") for key in keys), 3)  # g02, g03, g04 (M-C g01 excluded)
        self.assertNotIn("limitlessvgc:700", keys)  # the primary source already has that regional
        index = json.loads((self.current / "processed_events.json").read_text(encoding="utf-8"))
        self.assertEqual(index["regulation_id"], "M-D")
        self.assertTrue(all(not key.endswith("alpha-2027") for key in index["events"]))
        self.assertTrue(snapshot["early_meta"])
        megas = {row["mega"] for row in snapshot["megas"]}
        self.assertIn("heatran-mega", megas)  # from both the sheet slug and the online Heatranite

        # 4. Queries, the CLI, the freshness check and the weekly issue follow along.
        data = query.load(self.current)
        status = query.status(data, now=NEW_NOW)
        self.assertEqual(status["regulation_id"], "M-D")
        self.assertTrue(status["needs_refresh"])  # early meta is reported
        self.assertEqual(query.pokemon(data, "Mega Heatran")["usage"]["in_person"]["teams"], 2)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            self.assertEqual(meta_query.main(["--data-dir", str(self.current), "status"]), 0)
        self.assertIn("## Regulation M-D", buffer.getvalue())
        errors, _warnings = load_freshness().find_issues(self.root, now=NEW_NOW)
        self.assertEqual(errors, ())
        self.assertEqual(run_weekly.issue_title(summary), "Regulation changed: M-C -> M-D")
        self.assertIn("data/archive/M-C/", run_weekly.issue_body(summary, vgc_refresh.render(summary)))

        # 5. Nothing in the code, configuration or skills had to change.
        self.assertEqual(tree_digest("tools", "config", "skills"), before)

    def test_announcement_before_the_start_changes_nothing_yet(self) -> None:
        announced = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)

        class AnnouncedClient(NewRegulationClient):
            ROUTES = {
                **NewRegulationClient.ROUTES,
                OFFICIAL + "page/816.html": "regulation/official/page_816.html",
                VGCH + "data.js": "regulation/vgchistory/data_mc.js",
                CONFIG["sources"]["pikalytics"]["url"]: "regulation/pikalytics/pokedex_mc.md",
            }

        summary = vgc_refresh.refresh(config=self.config, client=AnnouncedClient(), now=announced, root=self.root)
        self.assertFalse(summary["regulation_changed"])
        self.assertEqual(summary["status"]["regulation_id"], "M-C")
        self.assertEqual(summary["status"]["next_regulation"]["regulation_id"], "M-D")
        self.assertFalse(self.archive.exists())
        self.assertIsNone(run_weekly.issue_title(summary))


if __name__ == "__main__":
    unittest.main()
