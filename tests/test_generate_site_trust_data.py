"""Tests for tools/generate_site_trust_data.py.

Modified by estebanmoreno04 (fork of NoahJenkins/vgc-coach): regulation facts
now come from the auto-detected data/current/regulation.json instead of a
hand-written current snapshot matched against a pinned registry entry.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools" / "generate_site_trust_data.py"


def load_module():
    spec = importlib.util.spec_from_file_location("generate_site_trust_data", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_repo_facts(root: Path) -> None:
    (root / "VERSION").write_text("0.2.0\n")
    eval_root = root / "data/fixtures/evals"
    for skill, cases in (("meta", 2), ("team", 1)):
        skill_root = eval_root / skill
        skill_root.mkdir(parents=True, exist_ok=True)
        for index in range(cases):
            (skill_root / f"case-{index + 1:02}.md").write_text("# Case\n")
    rubric_root = root / "data/rubrics"
    rubric_root.mkdir(parents=True)
    (rubric_root / "meta-rubric.md").write_text("# Rubric\n")
    (rubric_root / "human-review.md").write_text("# Human review\n")

    registry = root / "docs/skills/shared/references/live-source-registry.yaml"
    registry.parent.mkdir(parents=True)

    def source(source_id: str, role: str, priority: int, *, url: str) -> dict:
        return {
            "id": source_id,
            "display_name": source_id.replace("-", " ").title(),
            "role": role,
            "source_kind": "official" if role == "official_regulation" else "community",
            "canonical_url": url,
            "priority": priority,
            "allowed_claim_types": [
                "legality" if role == "official_regulation" else "current_snapshot"
            ],
            "required_for_minimum_stack": True,
            "freshness": {
                "max_age_days": 7,
                "policy": "Re-check live before current claims.",
            },
            "required_evidence_fields": ["source_url", "fetched_at"],
            "use_for": ["test claims"],
            "do_not_use_for": ["unsupported claims"],
            "fallback_if_unavailable": ["label the evidence gap"],
        }

    registry.write_text(
        yaml.safe_dump(
            {
                "version": "1",
                "summary": "Test source registry.",
                "usage": "Use test sources for generator validation.",
                "minimum_stack": {"official": 1, "tournament_meta": 1, "broader_meta": 1},
                "sources": [
                    source("official-test", "official_regulation", 1, url="https://example.com/rules"),
                    source("tournament-test", "tournament_meta", 2, url="https://example.com/tournament"),
                    source("broader-test", "broader_meta", 3, url="https://example.com/meta"),
                ],
            },
            sort_keys=False,
        )
    )
    write_regulation(root)


def write_regulation(root: Path, **changes) -> Path:
    current = root / "data/current"
    current.mkdir(parents=True, exist_ok=True)
    payload = {
        "regulation_id": "X-Y",
        "label": "Regulation Set X-Y",
        "active_window": {
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-12-31T23:59:59Z",
            "precision": "minute",
            "source_id": "official_news",
        },
        "official_url": "https://example.com/rules/x-y",
        "detected_at": "2026-08-01T00:00:00Z",
        "checked_at": "2026-08-06T12:34:56Z",
    }
    payload.update(changes)
    path = current / "regulation.json"
    path.write_text(json.dumps(payload))
    return path


class GenerateSiteTrustDataTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_collects_regulation_evals_and_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_repo_facts(root)

            facts = self.module.collect_trust_facts(
                root, now=datetime(2026, 8, 7, 12, 34, 56, tzinfo=timezone.utc)
            )

        self.assertEqual(facts["version"], "0.2.0")
        self.assertEqual(facts["evaluation"]["fixture_count"], 3)
        self.assertEqual(facts["evaluation"]["rubric_count"], 1)
        self.assertEqual(facts["evaluation"]["skill_count"], 2)
        self.assertEqual(facts["regulation"]["id"], "X-Y")
        self.assertEqual(facts["regulation"]["name"], "Regulation Set X-Y")
        self.assertEqual(facts["regulation"]["source_url"], "https://example.com/rules/x-y")
        self.assertEqual(facts["regulation"]["verified_on"], "2026-08-06")
        self.assertEqual(facts["regulation"]["verified_at"], "2026-08-06T12:34:56Z")
        self.assertEqual(facts["regulation"]["verified_label"], "August 6, 2026 at 12:34:56 UTC")
        self.assertEqual(facts["regulation"]["freshness_state"], "fresh")
        self.assertEqual(facts["regulation"]["freshness_max_age_days"], 7)
        self.assertEqual(facts["regulation"]["fresh_until"], "2026-08-13T12:34:56Z")
        self.assertIn("data/current/regulation.json", facts["generated_from"])
        self.assertEqual(len(facts["source_stack"]["required_sources"]), 3)
        self.assertEqual(facts["source_stack"]["status"], "configured")
        self.assertEqual(facts["calculation_boundary"]["exact"], ["damage", "KO", "survival", "speed"])
        self.assertEqual(facts["calculation_boundary"]["assumption_framed"], ["unrevealed opposing spreads"])

    def test_freshness_state_is_fresh_through_exact_max_age_boundary(self):
        boundary = datetime(2026, 8, 6, 12, 34, 56, tzinfo=timezone.utc) + timedelta(days=7)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_repo_facts(root)
            facts = self.module.collect_trust_facts(root, now=boundary)
        self.assertEqual(facts["regulation"]["freshness_state"], "fresh")

    def test_freshness_state_is_stale_after_max_age_boundary(self):
        after = datetime(2026, 8, 6, 12, 34, 56, tzinfo=timezone.utc) + timedelta(days=7, microseconds=1)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_repo_facts(root)
            facts = self.module.collect_trust_facts(root, now=after)
        self.assertEqual(facts["regulation"]["freshness_state"], "stale")
        self.assertEqual(facts["regulation"]["stale_label"], "Source snapshot stale")
        self.assertIn("live recheck", facts["regulation"]["freshness_note"])

    def test_requires_the_auto_detected_regulation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_repo_facts(root)
            (root / "data/current/regulation.json").unlink()
            with self.assertRaisesRegex(ValueError, "data/current/regulation.json"):
                self.module.collect_trust_facts(root)

    def test_open_ended_window_and_missing_official_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_repo_facts(root)
            write_regulation(
                root,
                active_window={"start": "2026-01-01T00:00:00Z", "end": None, "precision": "day", "source_id": "x"},
                official_url=None,
            )
            facts = self.module.collect_trust_facts(
                root, now=datetime(2026, 8, 7, tzinfo=timezone.utc)
            )
        self.assertIsNone(facts["regulation"]["ends_at"])
        self.assertEqual(facts["regulation"]["ends_label"], "not announced")
        self.assertEqual(facts["regulation"]["source_url"], "https://example.com/rules")

    def test_falls_back_to_detected_at_when_checked_at_is_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_repo_facts(root)
            write_regulation(root, checked_at=None)
            facts = self.module.collect_trust_facts(root)
        self.assertEqual(facts["regulation"]["verified_at"], "2026-08-01T00:00:00Z")

    def test_rejects_wrong_required_source_distribution_by_role(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_repo_facts(root)
            registry_path = root / "docs/skills/shared/references/live-source-registry.yaml"
            registry = yaml.safe_load(registry_path.read_text())
            registry["sources"][1]["role"] = "broader_meta"
            registry_path.write_text(yaml.safe_dump(registry, sort_keys=False))

            with self.assertRaisesRegex(ValueError, "minimum_stack.tournament_meta"):
                self.module.collect_trust_facts(root)

    def test_check_detects_committed_artifact_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_repo_facts(root)
            output = root / "site/src/generated/trustData.ts"
            output.parent.mkdir(parents=True)

            self.assertEqual(self.module.write_generated_artifact(root, output), 0)
            self.assertEqual(self.module.check_generated_artifact(root, output), 0)

            output.write_text(output.read_text().replace("0.2.0", "stale"))

            self.assertEqual(self.module.check_generated_artifact(root, output), 1)

    def test_check_rejects_artifact_after_freshness_boundary(self):
        fresh_check = datetime(2026, 8, 6, 12, 34, 56, tzinfo=timezone.utc) + timedelta(days=7)
        stale_check = fresh_check + timedelta(microseconds=1)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_repo_facts(root)
            output = root / "site/src/generated/trustData.ts"
            output.parent.mkdir(parents=True)

            self.assertEqual(self.module.write_generated_artifact(root, output, now=fresh_check), 0)
            self.assertEqual(self.module.check_generated_artifact(root, output, now=stale_check), 1)


if __name__ == "__main__":
    unittest.main()
