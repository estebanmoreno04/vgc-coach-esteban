"""Tests for tools/run_weekly.py and .github/workflows/weekly-refresh.yml."""

from __future__ import annotations

import io
import json
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "weekly-refresh.yml"
sys.path.insert(0, str(REPO_ROOT / "tools"))

import run_weekly  # noqa: E402


def summary(changed: bool = False) -> dict:
    return {
        "regulation_changed": changed,
        "previous_regulation_id": "X-Y" if changed else None,
        "status": {"regulation_id": "X-Z", "official_url": "https://example.com/x-z", "confidence": "high"},
        "regulation_warnings": [],
        "pipeline_warnings": [],
        "sources": [],
        "diff": {"comparable": not changed, "new_events": [{"key": "a"}, {"key": "b"}], "movers": {}},
    }


class WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        # PyYAML reads the `on:` key as boolean True.
        self.triggers = self.workflow.get("on", self.workflow.get(True))

    def test_runs_weekly_on_monday_morning_and_on_demand(self) -> None:
        self.assertEqual(self.triggers["schedule"], [{"cron": "0 6 * * 1"}])
        self.assertIn("workflow_dispatch", self.triggers)

    def test_permissions_are_limited_to_contents_and_issues(self) -> None:
        self.assertEqual(self.workflow["permissions"], {"contents": "write", "issues": "write"})

    def test_actions_are_pinned_to_commit_shas(self) -> None:
        steps = self.workflow["jobs"]["refresh"]["steps"]
        uses = [step["uses"] for step in steps if "uses" in step]
        self.assertTrue(uses)
        for reference in uses:
            self.assertRegex(reference, r"^[\w.-]+/[\w.-]+@[0-9a-f]{40}$")

    def test_steps_run_the_local_command_then_commit_and_open_issues(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("python3 tools/run_weekly.py", text)
        self.assertIn('["commit_message"]', text)
        self.assertIn("gh issue create", text)
        self.assertIsNone(re.search(r"\b[A-Z]-[A-Z]\b", text), "the workflow must not name a regulation")


class HelperTests(unittest.TestCase):
    def test_issue_only_when_the_regulation_changed(self) -> None:
        self.assertIsNone(run_weekly.issue_title(summary(changed=False)))
        self.assertEqual(run_weekly.issue_title(summary(changed=True)), "Regulation changed: X-Y -> X-Z")
        body = run_weekly.issue_body(summary(changed=True), "REPORT")
        self.assertIn("data/archive/X-Y/", body)
        self.assertIn("https://example.com/x-z", body)
        self.assertTrue(body.endswith("REPORT"))

    def test_commit_messages(self) -> None:
        self.assertEqual(
            run_weekly.commit_message(summary(), "2026-10-26"),
            "data: weekly refresh for X-Z (2026-10-26, 2 new events)",
        )
        self.assertEqual(
            run_weekly.commit_message(summary(changed=True), "2026-12-07"),
            "data: regulation changed to X-Z (2026-12-07)",
        )


class MainTests(unittest.TestCase):
    def run_main(self, *, changed: bool, validation_code: int, extra: list[str] | None = None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = Path(tmp.name)
        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)
            code = validation_code if "validate.py" in str(args[1]) else 0
            return mock.Mock(returncode=code)

        with mock.patch.object(run_weekly.vgc_refresh, "refresh", return_value=summary(changed)), \
                mock.patch.object(run_weekly.vgc_refresh, "render", return_value="# report"), \
                mock.patch.object(run_weekly.build_plugins, "build_all") as build_all, \
                mock.patch.object(run_weekly.subprocess, "run", side_effect=fake_run), \
                redirect_stdout(io.StringIO()):
            code = run_weekly.main(
                ["--now", "2026-12-07T06:00:00Z", "--summary-file", str(out / "s.json"), "--report-file", str(out / "r.md"),
                 *(extra or [])]
            )
        return code, json.loads((out / "s.json").read_text(encoding="utf-8")), calls, build_all

    def test_successful_run_writes_summary_and_report(self) -> None:
        code, written, calls, build_all = self.run_main(changed=True, validation_code=0)
        self.assertEqual(code, 0)
        self.assertEqual(written["issue_title"], "Regulation changed: X-Y -> X-Z")
        self.assertEqual(written["commit_message"], "data: regulation changed to X-Z (2026-12-07)")
        build_all.assert_called_once()
        self.assertTrue(any("generate_site_trust_data.py" in str(call[1]) for call in calls))
        self.assertTrue(any("validate.py" in str(call[1]) for call in calls))

    def test_failed_validation_blocks_the_commit(self) -> None:
        code, written, _calls, _build = self.run_main(changed=False, validation_code=1)
        self.assertEqual(code, 1)
        self.assertIsNone(written["issue_title"])

    def test_validation_can_be_skipped(self) -> None:
        code, _written, calls, _build = self.run_main(changed=False, validation_code=1, extra=["--no-validate"])
        self.assertEqual(code, 0)
        self.assertFalse(any("validate.py" in str(call[1]) for call in calls))

    def test_refresh_failure_exits_2(self) -> None:
        with mock.patch.object(run_weekly.vgc_refresh, "refresh", side_effect=RuntimeError("boom")), \
                io.StringIO() as err, mock.patch.object(sys, "stderr", err):
            self.assertEqual(run_weekly.main(["--now", "2026-12-07T06:00:00Z"]), 2)


if __name__ == "__main__":
    unittest.main()
