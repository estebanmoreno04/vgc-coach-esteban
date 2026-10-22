"""Tests for tools/build_coach_page.py and tools/coach_page/ (the shareable coach artifact)."""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))
sys.path.insert(0, str(REPO_ROOT / "tests"))

import build_coach_page  # noqa: E402
from test_build_snapshot import CLI as BUILD, CONFIG, FIXTURES, NOW, FixtureClient  # noqa: E402


TEAM = "Charizard @ Charizardite Y | Blaze | Modest | Heat Wave, Weather Ball, Solar Beam, Protect\nIncineroar @ Sitrus Berry | Intimidate | Careful | Fake Out, Parting Shot, Flare Blitz, Trick Room\n"
NODE = shutil.which("node")
DATA_RE = re.compile(r"const DATA = (\{[\s\S]*?\});\s*\n\s*const core =")


class CoachPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        root = Path(cls._tmp.name)
        config = copy.deepcopy(CONFIG)
        config["paths"]["snapshot_schema"] = str(REPO_ROOT / "data/schemas/meta-snapshot-v2.schema.json")
        config["pipeline"]["aggregation"].update(
            min_teams_to_rank_in_person=1, min_combo_teams=1, matchup_min_games=1, trend_recent_events=1
        )
        current = root / "data/current"
        current.mkdir(parents=True)
        shutil.copy(FIXTURES / "regulation.json", current / "regulation.json")
        BUILD.run(config=config, client=FixtureClient(), now=NOW, root=root)
        cls.output = build_coach_page.build(current, root / "coach.html", sprites=False)
        cls.html = cls.output.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_page_embeds_core_and_data(self) -> None:
        self.assertNotIn(build_coach_page.PLACEHOLDER, self.html)
        self.assertNotIn(build_coach_page.CORE_PLACEHOLDER, self.html)
        self.assertIn("VGCCoachCore", self.html)
        self.assertTrue(self.html.lstrip().startswith("<title>"))
        data = json.loads(re.search(r"const DATA = (\{[\s\S]*?\});\s*\n\s*const core =", self.html).group(1))
        self.assertEqual(data["regulation"]["id"], "M-C")
        self.assertEqual(data["usage"][0][0], "incineroar")
        self.assertIn("charizard-mega-y", data["dex"]["mega_base"])
        self.assertEqual(sorted(event[10] for event in data["by_event"]), ["in_person"] * 3 + ["online"])
        self.assertTrue(data["trend"]["available"])
        self.assertLess(len(self.html.encode("utf-8")), build_coach_page.MAX_PAGE_BYTES)

    def test_scripts_only_from_allowed_cdns_with_pinned_versions(self) -> None:
        sources = re.findall(r'<script src="([^"]+)"', self.html)
        self.assertTrue(sources)
        for src in sources:
            self.assertRegex(src, r"^https://cdn\.jsdelivr\.net/npm/@smogon/calc@\d+\.\d+\.\d+/")

    def test_sprite_names_and_embedding(self) -> None:
        import fetch_sprites

        self.assertEqual(fetch_sprites.candidates("charizard-mega-y")[0], "charizard-megay")
        self.assertIn("kommoo", fetch_sprites.candidates("kommo-o"))
        self.assertEqual(fetch_sprites.candidates("incineroar"), ["incineroar"])
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            (cache / "incineroar.png").write_bytes(b"\x89PNG fake")
            (cache / "manifest.json").write_text(json.dumps({"incineroar": {"file": "incineroar.png"}, "raichu-mega-y": {"file": None}}))
            sprites = build_coach_page.load_sprites(cache, {"incineroar", "raichu-mega-y", "kingambit"})
        self.assertEqual(set(sprites), {"incineroar"})
        self.assertEqual(json.loads(DATA_RE.search(self.html).group(1))["sprites"], {})

    def test_meta_sheet_has_no_fixed_prompts(self) -> None:
        self.assertNotIn("data-q=", self.html)
        self.assertIn('id="meta-home"', self.html)
        self.assertIn('id="history"', self.html)

    def test_template_and_core_name_no_regulation(self) -> None:
        for path in (build_coach_page.TEMPLATE, build_coach_page.CORE):
            self.assertIsNone(re.search(r"\b[A-Z]-[A-Z]\b", path.read_text(encoding="utf-8")), path.name)

    @unittest.skipUnless(NODE, "Node.js is not installed")
    def test_core_queries_run_on_the_embedded_data(self) -> None:
        completed = subprocess.run(
            [NODE, str(REPO_ROOT / "tests" / "coach_core_harness.cjs"), str(self.output)],
            input=TEAM, capture_output=True, text=True, encoding="utf-8", timeout=60, check=True,
        )
        out = json.loads(completed.stdout)
        self.assertEqual(out["usage"][0]["name"], "Incineroar")
        self.assertEqual(out["resolve"][0], {"species": "charizard", "mega": "charizard-mega-y"})
        self.assertIn("error", out["unknown"])
        members = {member["name"]: member for member in out["team"]["members"]}
        self.assertEqual(members["Charizard"]["mega"], "Charizard-Mega-Y")
        self.assertTrue(any("Trick Room" in note for note in members["Incineroar"]["notes"]))
        self.assertIn("calc_damage", out["tools"])
        self.assertIn("get_trend", out["tools"])
        self.assertIn("get_type_matchup", out["tools"])
        if isinstance(out["types"], dict) and "a" in out["types"]:
            self.assertEqual(out["types"]["a"]["form"], "Charizard-Mega-Y")
            self.assertEqual(sorted(out["types"]["b"]["types"]), ["Dark", "Steel"])
            self.assertTrue(all(hit["move"] not in ("Protect", "Tailwind") for hit in out["types"]["a_hits_b"] + out["types"]["b_hits_a"]))
        series = out["series"]
        self.assertEqual([event["date"] for event in series["events"]], sorted(event["date"] for event in series["events"]))
        self.assertEqual(len(series["series"][0]["values"]), len(series["events"]))
        self.assertEqual(series["series"][1]["values"], [0] * len(series["events"]))
        self.assertIn("get_event", out["tools"])
        self.assertTrue(out["trend"]["available"])
        self.assertTrue(out["event"]["usage"])
        self.assertIn("error", out["missing_event"])
        self.assertEqual(out["latest"], out["pokemon_by_event"][0]["event"])
        if isinstance(out["calc"], dict) and "damage" in out["calc"]:
            self.assertEqual(out["calc"]["damage"], [266, 314])
            self.assertEqual(out["speed"]["a"]["speed"], 368)


if __name__ == "__main__":
    unittest.main()
