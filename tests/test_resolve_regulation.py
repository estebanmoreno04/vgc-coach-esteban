"""Tests for the regulation resolver (tools/resolve_regulation.py).

All network access is replaced by fixtures under tests/fixtures/regulation.
Regulation identifiers appear only in those fixtures and in these tests.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "regulation"
sys.path.insert(0, str(REPO_ROOT / "tools"))

from vgc_data import jsliteral, text  # noqa: E402
from vgc_data.config import load_config  # noqa: E402
from vgc_data.http import PoliteClient, SourceBlocked, SourceError, HTTPStatusError  # noqa: E402
from vgc_data.resolver import ResolutionError  # noqa: E402


def load_cli():
    path = REPO_ROOT / "tools" / "resolve_regulation.py"
    spec = importlib.util.spec_from_file_location("resolve_regulation", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


CLI = load_cli()
CONFIG = load_config()
OFFICIAL = CONFIG["sources"]["official_news"]["base_url"]
LIMITLESS = CONFIG["sources"]["limitless_api"]["base_url"]
URLS = {
    "official_list": OFFICIAL + CONFIG["sources"]["official_news"]["list_path"],
    "vgchistory": CONFIG["sources"]["vgchistory"]["base_url"] + "data.js",
    "limitless_games": LIMITLESS + "games",
    "victory_road": CONFIG["sources"]["victory_road"]["url"],
    "pikalytics": CONFIG["sources"]["pikalytics"]["url"],
}


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=timezone.utc)


class FixtureClient:
    """Serves fixture files by URL; anything unmapped behaves like a dead source."""

    def __init__(
        self,
        *,
        official_list: str | None = None,
        official_pages: tuple[str, ...] = (),
        vgchistory: str | None = None,
        limitless: str | None = None,
        victory_road: str | None = None,
        pikalytics: str | None = None,
    ) -> None:
        self.routes: dict[str, str] = {}
        if official_list:
            self.routes[URLS["official_list"]] = f"official/{official_list}"
        for page in official_pages:
            self.routes[f"{OFFICIAL}page/{page}.html"] = f"official/page_{page}.html"
        if vgchistory:
            self.routes[URLS["vgchistory"]] = f"vgchistory/{vgchistory}"
        if limitless:
            self.routes[URLS["limitless_games"]] = "limitless/games.json"
        self.limitless = limitless
        if victory_road:
            self.routes[URLS["victory_road"]] = f"victory_road/{victory_road}"
        if pikalytics:
            self.routes[URLS["pikalytics"]] = f"pikalytics/{pikalytics}"
        self.requested: list[str] = []

    def get_text(self, url: str, *, ttl_hours: float = 0) -> str:
        self.requested.append(url)
        if self.limitless and url.startswith(LIMITLESS + "tournaments?"):
            if "page=1" in url:
                return (FIXTURES / "limitless" / self.limitless).read_text(encoding="utf-8")
            return "[]"
        if url in self.routes:
            return (FIXTURES / self.routes[url]).read_text(encoding="utf-8")
        raise SourceError(f"{url}: connection refused (fixture source down)")


def scenario_mc_normal() -> FixtureClient:
    return FixtureClient(
        official_list="list_current.json",
        official_pages=("816",),
        vgchistory="data_mc.js",
        limitless="tournaments_mc.json",
        victory_road="page_mc.html",
        pikalytics="pokedex_mc.md",
    )


def scenario_md_active() -> FixtureClient:
    return FixtureClient(
        official_list="list_with_md.json",
        official_pages=("816", "901"),
        vgchistory="data_md.js",
        limitless="tournaments_md.json",
        victory_road="page_with_md.html",
        pikalytics="pokedex_md.md",
    )


class ResolverScenarioTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.config = copy.deepcopy(CONFIG)
        self.config["paths"]["regulation_schema"] = str(
            REPO_ROOT / "data" / "schemas" / "regulation-v1.schema.json"
        )
        self.current = self.root / self.config["paths"]["current_dir"]
        self.archive = self.root / self.config["paths"]["archive_dir"]

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_resolver(self, client: FixtureClient, now: datetime):
        return CLI.run(config=self.config, client=client, now=now, root=self.root)

    def stored(self) -> dict:
        return json.loads((self.current / "regulation.json").read_text(encoding="utf-8"))

    def bootstrap_current(self) -> None:
        """Store the current regulation and a snapshot, as a previous run would."""
        self.run_resolver(scenario_mc_normal(), utc(2026, 10, 1, 9, 0))
        (self.current / "snapshot.json").write_text('{"fixture": "old snapshot"}\n', encoding="utf-8")
        (self.current / "processed_events.json").write_text("[]\n", encoding="utf-8")

    # (a) everything normal ------------------------------------------------

    def test_a_all_sources_agree(self) -> None:
        first = self.run_resolver(scenario_mc_normal(), utc(2026, 10, 1, 9, 0))
        second = self.run_resolver(scenario_mc_normal(), utc(2026, 10, 21, 12, 0))

        payload = self.stored()
        self.assertFalse(first.changed)
        self.assertFalse(second.changed)
        self.assertEqual(payload["regulation_id"], "M-C")
        self.assertEqual(payload["game"], "pokemon-champions")
        self.assertEqual(payload["confidence"], "high")
        self.assertFalse(payload["stale"])
        self.assertEqual(
            payload["agreeing_sources"],
            ["limitless_api", "official_news", "pikalytics", "vgchistory", "victory_road"],
        )
        self.assertEqual(
            payload["active_window"],
            {
                "start": "2026-09-09T02:00:00Z",
                "end": "2026-12-02T01:59:00Z",
                "precision": "minute",
                "source_id": "official_news",
            },
        )
        self.assertEqual(payload["mechanics"], ["mega-evolution"])
        self.assertEqual(payload["official_url"], f"{OFFICIAL}page/816.html")
        self.assertEqual(
            payload["rules"],
            {
                "held_items": {"duplicates_allowed": False},
                "timers_seconds": {"match": 1200, "player": 420, "turn": 45, "team_preview": 90},
            },
        )
        self.assertEqual(payload["detected_at"], "2026-10-01T09:00:00Z")
        self.assertEqual(payload["checked_at"], "2026-10-21T12:00:00Z")
        self.assertIsNone(payload["next_regulation"])
        self.assertEqual(payload["warnings"], [])
        self.assertFalse(self.archive.exists())

    def test_a_only_reads_live_official_articles(self) -> None:
        client = scenario_mc_normal()
        self.run_resolver(client, utc(2026, 10, 21, 12, 0))
        official_pages = [url for url in client.requested if "/page/" in url]
        self.assertEqual(official_pages, [f"{OFFICIAL}page/816.html"])

    # (b) regulation change ------------------------------------------------

    def test_b_change_archives_previous_snapshot(self) -> None:
        self.bootstrap_current()
        result = self.run_resolver(scenario_md_active(), utc(2026, 12, 10, 12, 0))

        payload = self.stored()
        self.assertTrue(result.changed)
        self.assertEqual(payload["regulation_id"], "M-D")
        self.assertEqual(payload["previous_regulation_id"], "M-C")
        self.assertEqual(payload["confidence"], "high")
        self.assertEqual(payload["active_window"]["start"], "2026-12-02T02:00:00Z")
        self.assertEqual(payload["official_url"], f"{OFFICIAL}page/901.html")
        self.assertEqual(payload["detected_at"], "2026-12-10T12:00:00Z")

        archived = self.archive / "M-C"
        self.assertEqual(
            sorted(path.name for path in archived.iterdir()),
            ["processed_events.json", "regulation.json", "snapshot.json"],
        )
        archived_regulation = json.loads((archived / "regulation.json").read_text(encoding="utf-8"))
        self.assertEqual(archived_regulation["regulation_id"], "M-C")
        self.assertEqual(archived_regulation["archived_at"], "2026-12-10T12:00:00Z")
        self.assertEqual(sorted(path.name for path in self.current.iterdir()), ["regulation.json"])
        self.assertTrue(any("archived" in warning for warning in payload["warnings"]))

    def test_b_second_change_does_not_overwrite_existing_archive(self) -> None:
        self.bootstrap_current()
        (self.archive / "M-C").mkdir(parents=True)
        (self.archive / "M-C" / "snapshot.json").write_text("{}", encoding="utf-8")
        self.run_resolver(scenario_md_active(), utc(2026, 12, 10, 12, 0))
        self.assertTrue((self.archive / "M-C-20261210T120000Z" / "snapshot.json").exists())
        self.assertEqual((self.archive / "M-C" / "snapshot.json").read_text(encoding="utf-8"), "{}")

    # (c) announced but not active ----------------------------------------

    def test_c_announced_regulation_is_recorded_as_next(self) -> None:
        self.bootstrap_current()
        client = FixtureClient(
            official_list="list_with_md.json",
            official_pages=("816", "901"),
            vgchistory="data_mc.js",
            limitless="tournaments_mc.json",
            victory_road="page_with_md.html",
            pikalytics="pokedex_md.md",  # switched early to the announced format
        )
        result = self.run_resolver(client, utc(2026, 11, 20, 12, 0))

        payload = self.stored()
        self.assertFalse(result.changed)
        self.assertEqual(payload["regulation_id"], "M-C")
        self.assertEqual(payload["confidence"], "high")
        self.assertEqual(payload["next_regulation"]["regulation_id"], "M-D")
        self.assertEqual(
            payload["next_regulation"]["expected_window"]["start"], "2026-12-02T02:00:00Z"
        )
        self.assertEqual(payload["next_regulation"]["sources"], ["official_news", "victory_road"])
        self.assertEqual(payload["next_regulation"]["official_url"], f"{OFFICIAL}page/901.html")
        self.assertTrue(
            any("Ignoring votes for M-D (pikalytics)" in warning for warning in payload["warnings"])
        )
        self.assertTrue((self.current / "snapshot.json").exists())
        self.assertFalse(self.archive.exists())

    # (d) sources in conflict ---------------------------------------------

    def test_d_conflict_keeps_stored_regulation(self) -> None:
        self.bootstrap_current()
        client = FixtureClient(
            official_list=None,  # official source down
            vgchistory="data_mc.js",
            limitless="tournaments_conflict.json",
            victory_road="page_mc.html",
            pikalytics="pokedex_md.md",
        )
        result = self.run_resolver(client, utc(2026, 11, 20, 12, 0))

        payload = self.stored()
        self.assertFalse(result.changed)
        self.assertEqual(payload["regulation_id"], "M-C")
        self.assertEqual(payload["confidence"], "low")
        self.assertTrue(any("disagree" in warning for warning in payload["warnings"]))
        self.assertTrue((self.current / "snapshot.json").exists())
        self.assertFalse(self.archive.exists())

    def test_d_official_date_settles_a_conflict(self) -> None:
        self.bootstrap_current()
        client = FixtureClient(
            official_list="list_with_md.json",
            official_pages=("901",),
            vgchistory="data_mc.js",  # still lists the old ruleset as present
            limitless="tournaments_mc.json",
            victory_road=None,
            pikalytics="pokedex_mc.md",  # lagging
        )
        result = self.run_resolver(client, utc(2026, 12, 3, 12, 0))

        payload = self.stored()
        self.assertTrue(result.changed)
        self.assertEqual(payload["regulation_id"], "M-D")
        self.assertEqual(payload["confidence"], "medium")
        self.assertTrue(any("still disagree" in warning for warning in payload["warnings"]))
        self.assertTrue((self.archive / "M-C" / "snapshot.json").exists())

    # (e) every source down -----------------------------------------------

    def test_e_all_sources_down_keeps_last_known_as_stale(self) -> None:
        self.bootstrap_current()
        before = self.stored()
        result = self.run_resolver(FixtureClient(), utc(2026, 10, 21, 12, 0))

        payload = self.stored()
        self.assertFalse(result.changed)
        self.assertTrue(payload["stale"])
        self.assertEqual(payload["regulation_id"], "M-C")
        self.assertEqual(payload["active_window"], before["active_window"])
        self.assertEqual(payload["checked_at"], "2026-10-21T12:00:00Z")
        self.assertTrue(all(source["status"] == "error" for source in payload["sources"]))
        self.assertTrue((self.current / "snapshot.json").exists())

    def test_e_all_sources_down_without_history_fails(self) -> None:
        with self.assertRaises(ResolutionError):
            self.run_resolver(FixtureClient(), utc(2026, 10, 21, 12, 0))
        self.assertFalse((self.current / "regulation.json").exists())

    def test_partial_outage_uses_remaining_sources(self) -> None:
        client = FixtureClient(
            vgchistory="data_mc.js",
            limitless="tournaments_mc.json",
            pikalytics="pokedex_mc.md",
        )
        self.run_resolver(client, utc(2026, 10, 21, 12, 0))
        payload = self.stored()
        self.assertEqual(payload["regulation_id"], "M-C")
        self.assertEqual(payload["confidence"], "high")
        self.assertEqual(payload["active_window"]["precision"], "month")
        self.assertIsNone(payload["official_url"])
        statuses = {source["source_id"]: source["status"] for source in payload["sources"]}
        self.assertEqual(statuses["official_news"], "error")
        self.assertEqual(statuses["victory_road"], "error")

    def test_dry_run_writes_nothing(self) -> None:
        CLI.run(
            config=self.config,
            client=scenario_mc_normal(),
            now=utc(2026, 10, 21, 12, 0),
            root=self.root,
            dry_run=True,
        )
        self.assertFalse(self.current.exists())


class TextHelperTests(unittest.TestCase):
    def test_regulation_ids_are_recognised_by_shape(self) -> None:
        self.assertEqual(text.regulation_ids_in("Regulation Set M-C (Updated on September 9)"), ["M-C"])
        self.assertEqual(text.regulation_ids_in("Pokemon Champions VGC 2026 Reg M-D"), ["M-D"])
        self.assertEqual(text.regulation_ids_in("Regulation Set M‑C"), ["M-C"])
        self.assertEqual(text.regulation_ids_in("Scarlet & Violet - Regulation I"), ["I"])
        self.assertEqual(text.regulation_ids_in("Regulation sets define which Pokémon"), [])
        self.assertEqual(text.regulation_id_from_format_code("gen9championsvgc2026regmd"), "M-D")
        self.assertEqual(text.regulation_id_from_format_code("gen9championsvgc2026regmbbo3"), "M-B")
        self.assertEqual(text.normalize_regulation_id("m-c"), "M-C")

    def test_date_parsers(self) -> None:
        self.assertEqual(
            text.parse_day_month_range("from 15 December to 3 March 2027"),
            (datetime(2026, 12, 15).date(), datetime(2027, 3, 3).date()),
        )
        self.assertEqual(
            text.parse_day_month_range("starting from 2 December 2026"),
            (datetime(2026, 12, 2).date(), None),
        )
        self.assertEqual(
            text.parse_utc_duration(
                "Wednesday, December 2, 2026, at 02:00 UTC to Wednesday, March 3, 2027, at 01:59 UTC"
            ),
            (utc(2026, 12, 2, 2, 0), utc(2027, 3, 3, 1, 59)),
        )
        self.assertEqual(
            text.parse_month_window("Jan 2024 – Apr 2024, then Dec 2025 – present")[2], True
        )
        self.assertEqual(text.first_date_in("October 31 – November 1, 2026"), datetime(2026, 10, 31).date())

    def test_mechanics_detection_ignores_negations(self) -> None:
        self.assertEqual(text.detect_mechanics("Mega Evolutions are allowed."), ["mega-evolution"])
        self.assertEqual(text.detect_mechanics("Terastallization is not allowed."), [])


class JsLiteralTests(unittest.TestCase):
    def test_parses_unquoted_keys_and_trailing_commas(self) -> None:
        source = "const A = 1;\nconst REGS = [ { id: 'X-Y', n: 2, ok: true, none: null, }, ];"
        self.assertEqual(
            jsliteral.extract_constant(source, "REGS"),
            [{"id": "X-Y", "n": 2, "ok": True, "none": None}],
        )

    def test_rejects_code(self) -> None:
        with self.assertRaises(ValueError):
            jsliteral.extract_constant("const T = [ fetch('x') ];", "T")


class RobotsTests(unittest.TestCase):
    def client(self, responses: dict[str, object]) -> PoliteClient:
        client = PoliteClient(user_agent="test-agent", sleep=lambda _: None)

        def fake_fetch(url: str, *, retries=None) -> str:
            outcome = responses[url]
            if isinstance(outcome, Exception):
                raise outcome
            return str(outcome)

        client._fetch = fake_fetch  # type: ignore[method-assign]
        return client

    def test_disallowed_path_is_blocked(self) -> None:
        client = self.client({"https://example.test/robots.txt": "User-agent: *\nDisallow: /private/\n"})
        with self.assertRaises(SourceBlocked):
            client.get_text("https://example.test/private/data.json")

    def test_missing_robots_allows_and_unreachable_robots_blocks(self) -> None:
        allowed = self.client(
            {
                "https://a.test/robots.txt": HTTPStatusError("https://a.test/robots.txt", 404),
                "https://a.test/data.json": "{}",
            }
        )
        self.assertEqual(allowed.get_text("https://a.test/data.json"), "{}")
        blocked = self.client({"https://b.test/robots.txt": HTTPStatusError("https://b.test/robots.txt", 503)})
        with self.assertRaises(SourceBlocked):
            blocked.get_text("https://b.test/data.json")


class NoHardcodedRegulationTests(unittest.TestCase):
    """Regulation ids may only appear in fixtures and tests."""

    CHECKED = (
        "config",
        "tools/resolve_regulation.py",
        "tools/build_snapshot.py",
        "tools/meta_query.py",
        "tools/vgc_refresh.py",
        "tools/damage_calc.py",
        "tools/calc/calc.mjs",
        "tools/check_format_freshness.py",
        "tools/generate_site_trust_data.py",
        "tools/render_source_registry_docs.py",
        "tools/vgc_data",
        "data/schemas/regulation-v1.schema.json",
        "data/schemas/meta-snapshot-v2.schema.json",
        "skills",
        ".opencode",
        "docs/skills",
        "docs/evals",
        "docs/runtime",
        "AGENTS.md",
        ".claude/CLAUDE.md",
    )
    TEXT_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".json"}

    def fixture_ids(self) -> set[str]:
        ids: set[str] = set()
        for path in FIXTURES.parent.rglob("*"):
            if path.is_file():
                ids.update(text.regulation_ids_in(path.read_text(encoding="utf-8")))
        return {reg for reg in ids if "-" in reg}

    def test_code_and_config_do_not_name_regulations(self) -> None:
        ids = self.fixture_ids()
        self.assertTrue(ids)
        patterns = [re.compile(rf"(?<![A-Za-z0-9]){re.escape(reg)}(?![A-Za-z0-9])", re.IGNORECASE) for reg in ids]
        patterns += [re.compile(rf"reg{reg.replace('-', '').lower()}\b") for reg in ids]
        offenders = []
        for relative in self.CHECKED:
            target = REPO_ROOT / relative
            files = [target] if target.is_file() else sorted(
                path for path in target.rglob("*") if path.is_file() and path.suffix in self.TEXT_SUFFIXES
            )
            for path in files:
                content = path.read_text(encoding="utf-8")
                for pattern in patterns:
                    if pattern.search(content):
                        offenders.append(f"{path.relative_to(REPO_ROOT)}: {pattern.pattern}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
