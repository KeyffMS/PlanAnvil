from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from _helpers import author_valid_plan, cleanup_worktree, start_fixture

from common import PlanAnvilError, atomic_write_json, load_json
from compare_review import compare_review
from map_instructions import map_instructions
from prepare_review_bundle import prepare_review_bundle
from record_analysis import record_analysis
from record_blind_review import record_blind_review
from validate_all import validate_all


class AnalysisAndReviewIntegrityTests(unittest.TestCase):
    def test_critical_unknown_blocks_before_plan_authoring(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = start_fixture(root, "Permanently remove all user data")
            try:
                map_instructions(
                    context["planning"],
                    affected_paths=["src/app.py"],
                    output=context["run_root"] / "evidence/instruction-map.json",
                )
                markdown = root / "analysis.md"
                markdown.write_text(
                    "# Goal analysis\n\nDeletion scope and retention policy are unknown.\n",
                    encoding="utf-8",
                    newline="\n",
                )
                data = root / "analysis.json"
                atomic_write_json(
                    data,
                    {
                        "classification": "STATEFUL",
                        "risk": "HIGH",
                        "affected_paths": ["src/app.py"],
                        "evidence": [f".pursue/runs/{context['run_id']}/evidence/original-goal.md"],
                        "assumptions": [],
                        "unknowns": [
                            {
                                "text": "Authoritative data-retention scope is unknown.",
                                "critical": True,
                                "verification": "Obtain the retention policy and approval owner.",
                            }
                        ],
                    },
                )
                result = record_analysis(
                    context["planning"], context["run_root"], analysis_markdown=markdown, analysis_data=data
                )
                self.assertFalse(result["ok"])
                self.assertEqual(result["result"], "BLOCKED_BY_CRITICAL_UNKNOWN")
                state = load_json(context["run_root"] / "state.json")
                self.assertEqual(state["status"], "BLOCKED")
                self.assertIn("BLOCKED_BY_CRITICAL_UNKNOWN", state["open_blockers"])
            finally:
                cleanup_worktree(context["source"], context["planning"], context["branch"])

    def test_review_bundle_rejects_tampering_and_failed_review_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = start_fixture(root)
            try:
                map_instructions(
                    context["planning"],
                    affected_paths=["src/app.py", "tests/test_app.py"],
                    output=context["run_root"] / "evidence/instruction-map.json",
                )
                author_valid_plan(context)
                validation = validate_all(
                    context["planning"], context["run_root"], source=context["source"], advance_state=True
                )
                self.assertTrue(validation["ok"], validation)
                prepare_review_bundle(context["planning"], context["run_root"])

                plan = context["run_root"] / "PLAN.md"
                original = plan.read_text(encoding="utf-8")
                plan.write_text(original + "\nTampered after bundling.\n", encoding="utf-8", newline="\n")
                review = root / "review.md"
                review.write_text("# Blind Plan Review\n\n## Result\n\n`PASS`\n", encoding="utf-8")
                with self.assertRaises(PlanAnvilError) as raised:
                    record_blind_review(
                        context["planning"], context["run_root"], review_markdown=review, result="PASS"
                    )
                self.assertEqual(raised.exception.code, "REVIEW_BUNDLE_CHANGED")
                plan.write_text(original, encoding="utf-8", newline="\n")

                failed_review = root / "failed-review.md"
                failed_review.write_text(
                    "# Blind Plan Review\n\n## Result\n\n`FAIL`\n\n## Findings\n\nRollback evidence is insufficient.\n",
                    encoding="utf-8",
                    newline="\n",
                )
                findings = root / "findings.json"
                atomic_write_json(
                    findings,
                    [{"id": "FINDING-01", "severity": "HIGH", "summary": "Rollback evidence is insufficient."}],
                )
                record_blind_review(
                    context["planning"],
                    context["run_root"],
                    review_markdown=failed_review,
                    result="FAIL",
                    findings_file=findings,
                )
                comparison = compare_review(context["planning"], context["run_root"])
                self.assertFalse(comparison["ok"])
                self.assertEqual(load_json(context["run_root"] / "state.json")["status"], "FAILED")
            finally:
                cleanup_worktree(context["source"], context["planning"], context["branch"])


if __name__ == "__main__":
    unittest.main()
