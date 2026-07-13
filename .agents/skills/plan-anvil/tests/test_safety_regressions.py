from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from _helpers import author_valid_plan, cleanup_worktree, init_repo, start_fixture
from artifact_policy import allowed_planning_path
from common import PlanAnvilError, atomic_write_json, atomic_write_text
from map_instructions import map_instructions
from prepare_review_bundle import prepare_review_bundle
from transition_state import run_lock
from validate_all import validate_all


class SafetyRegressionTests(unittest.TestCase):
    def test_immutable_writes_resume_only_for_equivalent_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            text_path = root / "report.md"
            atomic_write_text(text_path, "same\n", exclusive=True)
            atomic_write_text(text_path, "same\n", exclusive=True)
            with self.assertRaises(PlanAnvilError) as changed_text:
                atomic_write_text(text_path, "different\n", exclusive=True)
            self.assertEqual(changed_text.exception.code, "IMMUTABLE_EXISTS")

            json_path = root / "report.json"
            atomic_write_json(
                json_path,
                {"schema_version": "1.1.0", "created_at": "2026-01-01T00:00:00Z", "value": 1},
                exclusive=True,
            )
            atomic_write_json(
                json_path,
                {"schema_version": "1.1.0", "created_at": "2026-01-02T00:00:00Z", "value": 1},
                exclusive=True,
            )
            with self.assertRaises(PlanAnvilError) as changed_json:
                atomic_write_json(
                    json_path,
                    {"schema_version": "1.1.0", "created_at": "2026-01-02T00:00:00Z", "value": 2},
                    exclusive=True,
                )
            self.assertEqual(changed_json.exception.code, "IMMUTABLE_EXISTS")

    def test_same_process_does_not_bypass_an_active_run_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = init_repo(Path(directory) / "repo")
            run = repo / ".pursue/runs/test-run"
            run.mkdir(parents=True)
            state_path = run / "state.json"
            with run_lock(
                state_path,
                command="outer-test",
                stale_after_seconds=60,
                heartbeat_interval_seconds=10,
            ):
                with self.assertRaises(PlanAnvilError) as raised:
                    validate_all(repo, run)
                self.assertEqual(raised.exception.code, "GENERATION_LOCK_ACTIVE")

    def test_review_bundle_can_resume_after_partial_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context = start_fixture(Path(directory))
            try:
                map_instructions(
                    context["planning"],
                    affected_paths=["src/app.py", "tests/test_app.py"],
                    output=context["run_root"] / "evidence/instruction-map.json",
                )
                author_valid_plan(context)
                validation = validate_all(
                    context["planning"],
                    context["run_root"],
                    source=context["source"],
                    phase="pre-review",
                    advance_state=True,
                )
                self.assertTrue(validation["ok"], validation)

                first = prepare_review_bundle(
                    context["planning"],
                    context["run_root"],
                )
                self.assertTrue(first["ok"])
                prompt = context["run_root"] / "reports/plan-review/review-prompt.md"
                prompt.unlink()

                resumed = prepare_review_bundle(
                    context["planning"],
                    context["run_root"],
                )
                self.assertTrue(resumed["ok"])
                self.assertTrue(prompt.is_file())
            finally:
                cleanup_worktree(
                    context["source"],
                    context["planning"],
                    context["branch"],
                )

    def test_artifact_policy_rejects_unknown_run_payloads(self) -> None:
        run_rel = ".pursue/runs/example"
        accepted = [
            ".gitignore",
            ".pursue/SYSTEM_PROFILE.md",
            f"{run_rel}/PLAN.md",
            f"{run_rel}/evidence/analysis.json",
            f"{run_rel}/reports/validation/summary.json",
            f"{run_rel}/reports/plan-review/blind-review.md",
            f"{run_rel}/stages/STAGE-01.md",
            f"{run_rel}/risks/RISK-01-01.json",
        ]
        rejected = [
            f"{run_rel}/evidence/source.md",
            f"{run_rel}/reports/code.json",
            f"{run_rel}/logs/arbitrary.json",
            f"{run_rel}/incidents/source.php",
            f"{run_rel}/stages/helper.py",
            f"{run_rel}/local-state.json",
        ]
        for path in accepted:
            self.assertTrue(allowed_planning_path(path, run_rel), path)
        for path in rejected:
            self.assertFalse(allowed_planning_path(path, run_rel), path)


if __name__ == "__main__":
    unittest.main()
