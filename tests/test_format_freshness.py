"""Tests for tools/check_format_freshness.py.

Modified by estebanmoreno04 (fork of NoahJenkins/vgc-coach): the check now
validates data/current (auto-detected regulation and snapshot) instead of
hand-written registry entries, dated snapshots and legality notes.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools" / "check_format_freshness.py"
FIXTURE_REGULATION = REPO_ROOT / "tests" / "fixtures" / "snapshot" / "regulation.json"


def load_module():
    spec = importlib.util.spec_from_file_location("check_format_freshness", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=timezone.utc)


class FormatFreshnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        current = self.root / "data/current"
        current.mkdir(parents=True)
        schema = self.root / "data/schemas"
        schema.mkdir(parents=True)
        shutil.copy(REPO_ROOT / "data/schemas/regulation-v1.schema.json", schema / "regulation-v1.schema.json")
        self.regulation = json.loads(FIXTURE_REGULATION.read_text(encoding="utf-8"))
        self.write_regulation()
        self.write_snapshot(self.regulation["regulation_id"], "2026-10-20T00:00:00Z")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_regulation(self, **changes) -> None:
        payload = {**self.regulation, **changes}
        (self.root / "data/current/regulation.json").write_text(json.dumps(payload), encoding="utf-8")

    def write_snapshot(self, regulation_id: str, generated_at: str, early: bool = False) -> None:
        (self.root / "data/current/snapshot.json").write_text(
            json.dumps(
                {
                    "regulation": {"regulation_id": regulation_id},
                    "generated_at": generated_at,
                    "early_meta": early,
                }
            ),
            encoding="utf-8",
        )

    def issues(self, now: datetime):
        return self.module.find_issues(self.root, now=now)

    def test_current_data_inside_window_passes(self) -> None:
        errors, warnings = self.issues(utc(2026, 10, 21, 12))
        self.assertEqual(errors, ())
        self.assertEqual(warnings, ())

    def test_ended_window_warns_during_grace_then_fails(self) -> None:
        errors, warnings = self.issues(utc(2026, 12, 3, 12))
        self.assertEqual(errors, ())
        self.assertTrue(any("ended" in warning for warning in warnings))

        errors, _ = self.issues(utc(2026, 12, 12, 12))
        self.assertEqual(len(errors), 1)
        self.assertIn("run tools/vgc_refresh.py", errors[0])

    def test_snapshot_for_another_regulation_fails(self) -> None:
        self.write_snapshot("X-Y", "2026-10-20T00:00:00Z")
        errors, _ = self.issues(utc(2026, 10, 21, 12))
        self.assertEqual(len(errors), 1)
        self.assertIn("snapshot.json is for X-Y", errors[0])

    def test_old_or_early_snapshot_only_warns(self) -> None:
        self.write_snapshot(self.regulation["regulation_id"], "2026-10-01T00:00:00Z", early=True)
        errors, warnings = self.issues(utc(2026, 10, 21, 12))
        self.assertEqual(errors, ())
        self.assertTrue(any("days old" in warning for warning in warnings))
        self.assertTrue(any("early_meta" in warning for warning in warnings))

    def test_stale_or_low_confidence_regulation_only_warns(self) -> None:
        self.write_regulation(stale=True, confidence="low")
        errors, warnings = self.issues(utc(2026, 10, 21, 12))
        self.assertEqual(errors, ())
        self.assertEqual(len(warnings), 2)

    def test_missing_regulation_fails(self) -> None:
        (self.root / "data/current/regulation.json").unlink()
        errors, _ = self.issues(utc(2026, 10, 21, 12))
        self.assertIn("regulation.json is missing", errors[0])

    def test_invalid_regulation_is_rejected(self) -> None:
        self.write_regulation(confidence="certain")
        with self.assertRaisesRegex(ValueError, "schema"):
            self.issues(utc(2026, 10, 21, 12))

    def test_prompts_cannot_route_to_hand_written_notes_or_archive(self) -> None:
        skill = self.root / "skills/vgc-example/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            "Read `docs/skills/shared/references/champions-reg-x-y-legality.md`.\n"
            "Use data/archive/ for the meta.\n"
            "Never read data/archive/ for current answers.\n",
            encoding="utf-8",
        )
        errors, _ = self.issues(utc(2026, 10, 21, 12))
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("hand-written regulation note" in error for error in errors))
        self.assertTrue(any("routes coaching to data/archive/" in error for error in errors))

    def test_repository_data_is_consistent(self) -> None:
        regulation = json.loads((REPO_ROOT / "data/current/regulation.json").read_text(encoding="utf-8"))
        checked_at = datetime.fromisoformat(regulation["checked_at"].replace("Z", "+00:00"))
        errors, _ = self.module.find_issues(REPO_ROOT, now=checked_at)
        self.assertEqual(errors, ())


if __name__ == "__main__":
    unittest.main()
