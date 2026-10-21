"""Tests for tools/vgc_data/query.py, tools/meta_query.py and tools/vgc_refresh.py."""

from __future__ import annotations

import copy
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))
sys.path.insert(0, str(REPO_ROOT / "tests"))

import meta_query  # noqa: E402
import vgc_refresh  # noqa: E402
from test_build_snapshot import CLI as BUILD, CONFIG, FIXTURES, NOW, FixtureClient  # noqa: E402
from vgc_data import query  # noqa: E402


TEAM_LINES = """\
Charizard @ Charizardite Y | Blaze | Modest | Heat Wave, Weather Ball, Solar Beam, Protect
Incineroar @ Sitrus Berry | Intimidate | Careful | Fake Out, Parting Shot, Flare Blitz, Trick Room
Garchomp @ Life Orb | Rough Skin | Jolly | Earthquake, Dragon Claw, Rock Slide, Protect
"""

TEAM_SHOWDOWN = """\
Bob (Charizard) @ Charizardite Y
Ability: Blaze
Modest Nature
- Heat Wave
- Protect

Incineroar @ Sitrus Berry
Ability: Intimidate
- Fake Out
"""


class QueryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.config = copy.deepcopy(CONFIG)
        self.config["paths"]["snapshot_schema"] = str(REPO_ROOT / "data/schemas/meta-snapshot-v2.schema.json")
        self.config["pipeline"]["aggregation"].update(
            min_teams_to_rank_in_person=1, min_combo_teams=1, matchup_min_games=1
        )
        self.current = self.root / "data/current"
        self.current.mkdir(parents=True)
        shutil.copy(FIXTURES / "regulation.json", self.current / "regulation.json")
        BUILD.run(config=self.config, client=FixtureClient(), now=NOW, root=self.root)
        self.data = query.load(self.current)

    def tearDown(self) -> None:
        self._tmp.cleanup()


class QueryTests(QueryTestCase):
    def test_status_reports_data_basis_and_alerts(self) -> None:
        fresh = query.status(self.data, now=NOW)
        self.assertEqual(fresh["regulation_id"], "M-C")
        self.assertEqual(fresh["snapshot_age_days"], 0.0)
        self.assertTrue(fresh["early_meta"])  # the fixture has only 15 teams
        self.assertTrue(fresh["needs_refresh"])

        later = query.status(self.data, now=datetime(2026, 11, 5, tzinfo=timezone.utc))
        self.assertTrue(any("days old" in alert for alert in later["alerts"]))
        ended = query.status(self.data, now=datetime(2026, 12, 5, tzinfo=timezone.utc))
        self.assertTrue(any("window ended" in alert for alert in ended["alerts"]))

    def test_species_names_resolve_in_many_spellings(self) -> None:
        self.assertEqual(query.resolve_species(self.data, "Mega Charizard Y"), ("charizard", "charizard-mega-y"))
        self.assertEqual(query.resolve_species(self.data, "charizard-mega-y"), ("charizard", "charizard-mega-y"))
        self.assertEqual(query.resolve_species(self.data, "Basculegion-F"), ("basculegion-f", None))
        self.assertEqual(query.resolve_species(self.data, "Incineroarr"), ("incineroar", None))
        with self.assertRaisesRegex(query.QueryError, "does not appear"):
            query.resolve_species(self.data, "Pikachu")

    def test_pokemon_usage_and_top_cut(self) -> None:
        info = query.pokemon(self.data, "Incineroar")
        self.assertEqual(info["usage"]["in_person"]["teams"], 9)
        self.assertEqual(info["sets"]["items"][0]["name"], "Sitrus Berry")
        self.assertGreater(info["top_cut_appearances"], 0)
        rows = query.top_cut(self.data, segment="online", species="Raichu")
        self.assertEqual([row["player"] for row in rows], ["OnlineOne"])

    def test_trend_and_single_event(self) -> None:
        self.assertFalse(query.trend(self.data)["available"])  # two whole-field events only
        info = query.event(self.data, "alpha")
        self.assertEqual(info["key"], "vgchistory:regional-alpha-2027")
        self.assertEqual(info["basis"], "full_field")
        self.assertTrue(info["usage"])
        self.assertTrue(all(team["event_key"] == info["key"] for team in info["top_cut"]))
        with self.assertRaisesRegex(query.QueryError, "Events in the snapshot"):
            query.event(self.data, "Atlantis")
        by_event = query.pokemon(self.data, "Incineroar")["by_event"]
        self.assertTrue(by_event)
        self.assertTrue(all("share" in row and "event" in row for row in by_event))

    def test_team_parsing_formats(self) -> None:
        lines = query.parse_team(TEAM_LINES)
        self.assertEqual(
            lines[0],
            {
                "name": "Charizard",
                "item": "Charizardite Y",
                "ability": "Blaze",
                "nature": "Modest",
                "moves": ["Heat Wave", "Weather Ball", "Solar Beam", "Protect"],
            },
        )
        showdown = query.parse_team(TEAM_SHOWDOWN)
        self.assertEqual([mon["name"] for mon in showdown], ["Charizard", "Incineroar"])
        self.assertEqual(showdown[0]["nature"], "Modest")
        self.assertEqual(showdown[1]["moves"], ["Fake Out"])

    def test_team_report(self) -> None:
        report = query.team(self.data, TEAM_LINES)
        members = {member["species"]: member for member in report["members"]}
        self.assertEqual(members["charizard"]["mega"], "charizard-mega-y")
        self.assertTrue(any("Trick Room" in note for note in members["incineroar"]["notes"]))
        cores = [combo["species"] for combo in report["cores_seen_in_meta"]["in_person"]]
        self.assertIn(["garchomp", "incineroar"], cores)

    def test_archive_is_refused(self) -> None:
        archived = self.root / "data/archive/X-Y"
        archived.mkdir(parents=True)
        shutil.copy(self.current / "regulation.json", archived / "regulation.json")
        with self.assertRaisesRegex(query.QueryError, "archive"):
            query.load(archived)

    def test_snapshot_must_match_regulation(self) -> None:
        regulation = json.loads((self.current / "regulation.json").read_text(encoding="utf-8"))
        regulation["regulation_id"] = "X-Y"
        (self.current / "regulation.json").write_text(json.dumps(regulation), encoding="utf-8")
        with self.assertRaisesRegex(query.QueryError, "run tools/vgc_refresh.py"):
            query.load(self.current)

    def test_diff_reports_new_events_and_movers(self) -> None:
        new = json.loads((self.current / "snapshot.json").read_text(encoding="utf-8"))
        old = copy.deepcopy(new)
        old["events"] = old["events"][:-1]
        for row in old["usage"]:
            if row["species"] == "incineroar":
                row["in_person"]["share"] = 0.5
        diff = query.diff_snapshots(old, new)
        self.assertTrue(diff["comparable"])
        self.assertEqual([event["key"] for event in diff["new_events"]], [new["events"][-1]["key"]])
        self.assertEqual(diff["movers"]["in_person"]["up"][0]["species"], "incineroar")
        other = copy.deepcopy(new)
        other["regulation"]["regulation_id"] = "X-Y"
        self.assertFalse(query.diff_snapshots(other, new)["comparable"])


class CliTests(QueryTestCase):
    def run_cli(self, *args: str) -> str:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = meta_query.main(["--data-dir", str(self.current), *args])
        self.assertEqual(code, 0)
        return buffer.getvalue()

    def test_markdown_and_json_outputs(self) -> None:
        self.assertIn("## Regulation M-C", self.run_cli("status"))
        self.assertIn("| 1 | Incineroar |", self.run_cli("usage", "--top", "3"))
        self.assertIn("## Charizard", self.run_cli("pokemon", "Mega Charizard Y"))
        payload = json.loads(self.run_cli("--json", "usage", "--segment", "online", "--top", "2"))
        self.assertEqual(len(payload), 2)

    def test_refresh_offline_summary(self) -> None:
        summary = vgc_refresh.refresh(config=self.config, client=FixtureClient(), now=NOW, root=self.root, offline=True)
        text = vgc_refresh.render(summary)
        self.assertIn("# VGC refresh — regulation M-C", text)
        self.assertIn("None since the last refresh.", text)
        self.assertIn("Early meta", text)


if __name__ == "__main__":
    unittest.main()
