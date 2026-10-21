"""Tests for the meta pipeline (tools/build_snapshot.py), using fixtures only."""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "snapshot"
sys.path.insert(0, str(REPO_ROOT / "tools"))

from vgc_data.config import load_config  # noqa: E402
from vgc_data.http import HTTPStatusError, SourceError  # noqa: E402
from vgc_data.pokedex import Pokedex, name_key  # noqa: E402


def load_cli():
    path = REPO_ROOT / "tools" / "build_snapshot.py"
    spec = importlib.util.spec_from_file_location("build_snapshot", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


CLI = load_cli()
CONFIG = load_config()
VGCH = CONFIG["pipeline"]["sources"]["vgchistory"]["base_url"]
LVGC = CONFIG["pipeline"]["sources"]["limitlessvgc"]["base_url"]
LIMITLESS = CONFIG["pipeline"]["sources"]["limitless_api"]["base_url"]
NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


class FixtureClient:
    def __init__(self, *, data_js: str | None = "data.js", extra: dict[str, str] | None = None) -> None:
        self.routes = {
            f"{VGCH}standings/regional-alpha-2027.json": "vgchistory/standings_alpha.json",
            f"{VGCH}sheets/regional-alpha-2027.json": "vgchistory/sheets_alpha.json",
            f"{VGCH}matches/regional-alpha-2027.json": "vgchistory/matches_alpha.json",
            f"{VGCH}standings/regional-beta-2027.json": "vgchistory/standings_beta.json",
            f"{LVGC}tournaments": "limitlessvgc/tournaments.html",
            f"{LVGC}tournaments/500/teams": "limitlessvgc/teams_500.html",
            f"{LIMITLESS}games": "../regulation/limitless/games.json",
            f"{LIMITLESS}tournaments/onl1/details": "limitless/details_onl1.json",
            f"{LIMITLESS}tournaments/onl1/standings": "limitless/standings_onl1.json",
            f"{LIMITLESS}tournaments/loc1/details": "limitless/details_loc1.json",
        }
        if data_js:
            self.routes[f"{VGCH}data.js"] = f"vgchistory/{data_js}"
        self.routes.update(extra or {})
        self.requested: list[str] = []

    def get_text(self, url: str, *, ttl_hours: float = 0) -> str:
        self.requested.append(url)
        if url.startswith(f"{LIMITLESS}tournaments?"):
            return (FIXTURES / "limitless" / "tournaments.json").read_text(encoding="utf-8") if "page=1" in url else "[]"
        if url in self.routes:
            return (FIXTURES / self.routes[url]).read_text(encoding="utf-8")
        if url.startswith(VGCH):
            raise HTTPStatusError(url, 404)
        raise SourceError(f"{url}: fixture source down")


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.config = copy.deepcopy(CONFIG)
        self.config["paths"]["snapshot_schema"] = str(REPO_ROOT / "data/schemas/meta-snapshot-v2.schema.json")
        aggregation = self.config["pipeline"]["aggregation"]
        aggregation.update(min_teams_to_rank_in_person=1, min_combo_teams=1, matchup_min_games=1)
        self.current = self.root / self.config["paths"]["current_dir"]
        self.current.mkdir(parents=True)
        shutil.copy(FIXTURES / "regulation.json", self.current / "regulation.json")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def build(self, client: FixtureClient, now: datetime = NOW):
        return CLI.run(config=self.config, client=client, now=now, root=self.root)

    @staticmethod
    def usage(payload: dict, species: str) -> dict:
        return next(row for row in payload["usage"] if row["species"] == species)

    def test_builds_segmented_snapshot(self) -> None:
        result = self.build(FixtureClient())
        payload = result.payload

        self.assertEqual(payload["regulation"]["regulation_id"], "M-C")
        self.assertEqual(
            payload["segments"],
            {
                "in_person": {"events": 3, "full_field_events": 2, "teams": 12, "day2_teams": 4},
                "online": {"events": 1, "teams": 3},
                "total": {"events": 3, "teams": 15},
            },
        )
        incineroar = self.usage(payload, "incineroar")
        self.assertEqual(
            incineroar["in_person"],
            {
                "teams": 9,
                "share": 0.75,
                "win_rate": 0.5152,
                "games": 33,
                "day2_teams": 2,
                "day2_share": 0.5,
                "day2_conversion": 0.2857,
                "top_cut_teams": 9,
            },
        )
        self.assertEqual(incineroar["online"], {"teams": 2, "share": 0.6667, "win_rate": 0.75, "games": 12})
        self.assertEqual(incineroar["total"], {"teams": 11, "share": 0.7333, "win_rate": 0.5778, "games": 45})
        self.assertEqual(payload["usage"][0]["species"], "incineroar")
        self.assertEqual(self.usage(payload, "kommo-o")["name"], "Kommo-o")
        self.assertEqual(self.usage(payload, "basculegion-f")["name"], "Basculegion-F")

    def test_megas_are_normalized_across_sources(self) -> None:
        payload = self.build(FixtureClient()).payload
        megas = {row["mega"]: row for row in payload["megas"]}
        self.assertEqual(megas["raichu-mega-y"]["in_person"]["teams"], 2)
        self.assertEqual(megas["raichu-mega-y"]["online"]["teams"], 1)  # Raichu holding Raichunite Y
        self.assertEqual(megas["floette-mega"]["online"]["teams"], 1)  # Floette-Eternal holding Floettite
        self.assertEqual(megas["charizard-mega-y"]["online"]["teams"], 1)
        self.assertEqual(megas["floette-mega"]["name"], "Floette-Mega")
        self.assertNotIn("dusclops-mega", megas)  # Eviolite is not a Mega Stone
        floette = self.usage(payload, "floette-eternal")
        self.assertEqual(floette["total"]["teams"], 2)

    def test_sets_pairs_matchups_and_top_cut(self) -> None:
        payload = self.build(FixtureClient()).payload
        sets = {row["species"]: row for row in payload["sets"]}
        incineroar = sets["incineroar"]
        self.assertEqual(incineroar["sample"], 5)  # 3 in-person sheets + 2 online lists
        self.assertEqual(incineroar["items"][0], {"name": "Sitrus Berry", "count": 3, "share": 0.6})
        self.assertEqual(incineroar["moves"][0]["name"], "Fake Out")
        self.assertEqual(incineroar["moves"][0]["share"], 1.0)
        self.assertEqual(sets["raichu"]["megas"][0]["mega"], "raichu-mega-y")

        top_pair = payload["pairs"]["in_person"][0]
        self.assertEqual(top_pair["species"], ["garchomp", "incineroar"])
        self.assertEqual(top_pair["teams"], 7)

        self.assertEqual(payload["matchups"]["matches"], 13)
        pairs = {(row["species"], row["opponent"]): row for row in payload["matchups"]["pairs"]}
        # Charizard teams (Bob, Eve) vs Raichu teams (Alice, Carl): Bob beat Carl
        # and Alice, Eve lost to Alice.
        self.assertEqual(
            (pairs[("charizard", "raichu")]["wins"], pairs[("charizard", "raichu")]["games"]), (2, 3)
        )
        self.assertEqual(pairs[("raichu", "charizard")]["wins"], 1)

        first = payload["top_cut_teams"][0]
        self.assertEqual((first["event"], first["placement"], first["player"]), ("Regional Gamma", 1, "Mia Example"))
        bob = next(row for row in payload["top_cut_teams"] if row["player"] == "Bob Example")
        self.assertEqual(bob["record"], "4-0")
        self.assertEqual(bob["team"][0]["mega"], "Charizard-Mega-Y")
        online = [row for row in payload["top_cut_teams"] if row["segment"] == "online"]
        self.assertEqual([row["player"] for row in online], ["OnlineOne", "OnlineTwo", "OnlineThree"])

    def test_events_sources_and_early_meta(self) -> None:
        payload = self.build(FixtureClient()).payload
        keys = [event["key"] for event in payload["events"]]
        self.assertEqual(
            keys,
            ["vgchistory:regional-alpha-2027", "vgchistory:regional-beta-2027", "limitlessvgc:500", "limitless_api:onl1"],
        )
        runs = {source["source_id"]: source for source in payload["sources"]}
        self.assertEqual(runs["vgchistory"]["new_events"], 2)
        self.assertEqual(runs["limitlessvgc"]["new_events"], 1)  # Alpha is skipped: VGC History has it
        self.assertEqual(runs["limitless_api"]["new_events"], 1)
        self.assertEqual(runs["limitless_api"]["skipped"], 1)  # in-person local event
        self.assertTrue(payload["early_meta"])
        self.assertEqual(len(payload["early_meta_reasons"]), 1)  # 15 teams < 1000; 3 in-person events is enough
        self.assertTrue(any("fallback" in warning for warning in payload["warnings"]))
        alpha = payload["events"][0]
        self.assertEqual(alpha["coverage"]["teams_with_sets"], 4)
        self.assertTrue(alpha["coverage"]["day2"])
        self.assertTrue((self.current / "snapshot.json").exists())
        self.assertTrue((self.current / "pokedex.json").exists())

    def test_usage_per_event_and_trend(self) -> None:
        payload = self.build(FixtureClient()).payload
        by_event = payload["by_event"]
        self.assertEqual([event["date"] for event in by_event], sorted((event["date"] for event in by_event), reverse=True))
        segments = payload["segments"]
        self.assertEqual(len(by_event), segments["in_person"]["events"] + segments["online"]["events"])
        online = next(event for event in by_event if event["segment"] == "online")
        self.assertLessEqual(len(online["top_teams"]), self.config["pipeline"]["aggregation"]["online_top_cut"])
        self.assertTrue(all(team["placement"] <= 4 for team in online["top_teams"]))
        bases = {event["key"]: event["basis"] for event in by_event}
        self.assertEqual(bases["limitlessvgc:500"], "day2_only")
        self.assertEqual(bases["vgchistory:regional-alpha-2027"], "full_field")
        alpha = next(event for event in by_event if event["key"] == "vgchistory:regional-alpha-2027")
        self.assertGreater(alpha["teams"], 0)
        self.assertTrue(all(row["share"] == round(row["teams"] / alpha["teams"], 4) for row in alpha["usage"]))
        # Two whole-field events and two "recent" ones: nothing earlier to compare with.
        self.assertFalse(payload["trend"]["available"])

        self.config["pipeline"]["aggregation"]["trend_recent_events"] = 1
        trend = self.build(FixtureClient()).payload["trend"]
        self.assertTrue(trend["available"])
        self.assertEqual([event["key"] for event in trend["recent_events"]], ["vgchistory:regional-beta-2027"])
        self.assertEqual([event["key"] for event in trend["earlier_events"]], ["vgchistory:regional-alpha-2027"])
        beta = {row["species"]: row for row in next(e for e in by_event if e["key"] == "vgchistory:regional-beta-2027")["usage"]}
        alpha_rows = {row["species"]: row for row in alpha["usage"]}
        for row in trend["species"]:
            self.assertEqual(row["recent"]["share"], beta[row["id"]]["share"] if row["id"] in beta else 0.0)
            self.assertEqual(row["earlier"]["share"], alpha_rows[row["id"]]["share"] if row["id"] in alpha_rows else 0.0)
        deltas = [row["share_delta"] for row in trend["species"]]
        self.assertEqual(deltas, sorted(deltas, reverse=True))

    def test_second_run_is_incremental(self) -> None:
        first = self.build(FixtureClient()).payload
        client = FixtureClient()
        second = self.build(client).payload
        event_requests = [
            url for url in client.requested
            if any(part in url for part in ("standings", "sheets", "matches", "/teams", "/details"))
        ]
        self.assertEqual(event_requests, [])
        self.assertEqual(first["usage"], second["usage"])
        self.assertTrue(all(source["new_events"] == 0 for source in second["sources"]))

    def test_old_online_events_leave_the_window(self) -> None:
        self.build(FixtureClient())
        later = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
        payload = self.build(FixtureClient(), later).payload
        self.assertEqual(payload["segments"]["online"], {"events": 0, "teams": 0})
        self.assertEqual(payload["segments"]["in_person"]["events"], 3)
        index = json.loads((self.current / "processed_events.json").read_text(encoding="utf-8"))["events"]
        self.assertNotIn("limitless_api:onl1", index)
        self.assertNotIn("limitless_api:loc1", index)
        self.assertFalse((self.current / "events" / "limitless_api" / "onl1.json.gz").exists())

    def test_fallback_event_is_replaced_when_primary_source_has_it(self) -> None:
        self.build(FixtureClient())
        self.assertTrue((self.current / "events" / "limitlessvgc" / "500.json.gz").exists())
        client = FixtureClient(
            data_js="data_with_gamma.js",
            extra={f"{VGCH}standings/regional-gamma-2027.json": "vgchistory/standings_gamma.json"},
        )
        payload = self.build(client, datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)).payload
        keys = [event["key"] for event in payload["events"]]
        self.assertIn("vgchistory:regional-gamma-2027", keys)
        self.assertNotIn("limitlessvgc:500", keys)
        self.assertFalse((self.current / "events" / "limitlessvgc" / "500.json.gz").exists())

    def test_primary_source_down_uses_fallback(self) -> None:
        payload = self.build(FixtureClient(data_js=None)).payload
        runs = {source["source_id"]: source for source in payload["sources"]}
        self.assertEqual(runs["vgchistory"]["status"], "error")
        self.assertEqual(runs["limitlessvgc"]["new_events"], 1)
        self.assertEqual(len(runs["limitlessvgc"]["errors"]), 1)  # Alpha's teams page is unavailable
        self.assertTrue(any("VGC History is unavailable" in warning for warning in payload["warnings"]))

    def test_dry_run_downloads_and_writes_nothing(self) -> None:
        client = FixtureClient()
        result = CLI.run(config=self.config, client=client, now=NOW, root=self.root, dry_run=True)
        self.assertEqual(client.requested, [])
        self.assertIsNone(result.path)
        self.assertFalse((self.current / "snapshot.json").exists())

    def test_sets_keep_a_day2_block_with_proven_options(self) -> None:
        payload = self.build(FixtureClient()).payload
        for row in payload["sets"]:
            day2 = row["day2"]
            self.assertLessEqual(day2["sample"], row["in_person_sample"])
            seen = {move["name"] for move in day2["moves"]}
            self.assertTrue(all(move["count"] <= day2["sample"] for move in day2["moves"]))
            if day2["sample"]:
                self.assertTrue(seen)
        self.assertTrue(any(row["day2"]["sample"] for row in payload["sets"]))

    def test_offline_rebuild_keeps_the_last_source_report(self) -> None:
        downloaded = self.build(FixtureClient()).payload["sources"]
        self.assertTrue(downloaded)
        client = FixtureClient()
        offline = CLI.run(config=self.config, client=client, now=NOW, root=self.root, offline=True).payload
        self.assertEqual(client.requested, [])
        self.assertEqual(offline["sources"], downloaded)

    def test_refuses_events_from_another_regulation(self) -> None:
        (self.current / "processed_events.json").write_text(
            json.dumps({"regulation_id": "M-B", "events": {}}), encoding="utf-8"
        )
        with self.assertRaises(CLI.PipelineError):
            self.build(FixtureClient())

    def test_requires_a_resolved_regulation(self) -> None:
        (self.current / "regulation.json").unlink()
        with self.assertRaises(CLI.PipelineError):
            self.build(FixtureClient())


class PokedexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dex = Pokedex.from_vgchistory(
            {
                "charizard-mega-x": {"base": "charizard", "tfrom": "charizard", "ps": "Charizard-Mega-X"},
                "charizard-mega-y": {"base": "charizard", "tfrom": "charizard", "ps": "Charizard-Mega-Y"},
                "garchomp-mega": {"base": "garchomp", "tfrom": "garchomp", "ps": "Garchomp-Mega"},
                "garchomp-mega-z": {"base": "garchomp", "tfrom": "garchomp", "ps": "Garchomp-Mega-Z"},
            }
        )

    def test_stone_letters_select_the_right_form(self) -> None:
        self.assertEqual(self.dex.identity("charizard", "Charizardite Y"), ("charizard", "charizard-mega-y"))
        self.assertEqual(self.dex.identity("garchomp", "Garchompite"), ("garchomp", "garchomp-mega"))
        self.assertEqual(self.dex.identity("garchomp", "Garchompite Z"), ("garchomp", "garchomp-mega-z"))
        self.assertEqual(self.dex.identity("garchomp-mega-z"), ("garchomp", "garchomp-mega-z"))
        self.assertEqual(self.dex.identity("garchomp", "Life Orb"), ("garchomp", None))
        self.assertEqual(self.dex.identity("porygon2", "Eviolite"), ("porygon2", None))

    def test_unknown_species_without_registry_uses_stone_name(self) -> None:
        self.assertEqual(Pokedex().identity("Heatran", "Heatranite"), ("heatran", "heatran-mega"))
        self.assertEqual(Pokedex().display("slowking-galar"), "Slowking-Galar")
        self.assertEqual(Pokedex().display("kommo-o"), "Kommo-o")

    def test_name_keys_merge_spelling_variants(self) -> None:
        self.assertEqual(name_key("Trick-or-Treat"), name_key("Trick or Treat"))
        self.assertEqual(name_key("King’s Rock"), name_key("King's Rock"))


if __name__ == "__main__":
    unittest.main()
