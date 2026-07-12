from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _helpers import author_valid_plan, cleanup_worktree, start_fixture

from commit_plan import commit_plan
from compare_review import compare_review
from map_instructions import map_instructions
from prepare_review_bundle import prepare_review_bundle
from record_blind_review import record_blind_review
from validate_all import validate_all


class ValidationReviewCommitTests(unittest.TestCase):
    def test_end_to_end_plan_generation_stops_without_implementation(self) -> None:
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
                    context["planning"],
                    context["run_root"],
                    source=context["source"],
                    phase="pre-review",
                    advance_state=True,
                )
                self.assertTrue(validation["ok"], validation)

                bundle = prepare_review_bundle(context["planning"], context["run_root"])
                self.assertTrue(bundle["ok"])
                review_source = root / "review.md"
                review_source.write_text(
                    """# Blind Plan Review

## Result

`PASS`

## Scope reviewed

Goal, profile, instructions, plan, stage, traceability, risk, and deterministic validation.

## Findings

No blocking findings.

## Traceability and acceptance review

The critical requirement reaches automated evidence through a stage, criterion, risk, and control.

## Testing, rollback, and approvals

The expected-red cycle, full green verification, rollback, and base-integration approval are explicit.

## Generator/executor boundary

The generator stops and requires a separate execution run.

## Conclusion

PASS.
""",
                    encoding="utf-8",
                    newline="\n",
                )
                findings = root / "findings.json"
                findings.write_text("[]\n", encoding="utf-8")
                recorded = record_blind_review(
                    context["planning"],
                    context["run_root"],
                    review_markdown=review_source,
                    result="PASS",
                    findings_file=findings,
                )
                self.assertEqual(recorded["review_result"], "PASS")
                comparison = compare_review(context["planning"], context["run_root"])
                self.assertTrue(comparison["ok"], comparison)

                result = commit_plan(
                    context["planning"],
                    context["run_root"],
                    source=context["source"],
                )
                self.assertEqual(result["result"], "STOPPED")
                self.assertFalse(result["implementation_executed"])
                self.assertFalse(result["pushed"])
                self.assertTrue((context["run_root"] / "final/REPORT.md").is_file())
                self.assertEqual(
                    __import__("subprocess").run(
                        ["git", "-C", str(context["source"]), "status", "--porcelain"],
                        text=True,
                        stdout=__import__("subprocess").PIPE,
                        check=True,
                    ).stdout,
                    "",
                )
                self.assertEqual(
                    __import__("subprocess").run(
                        ["git", "-C", str(context["planning"]), "status", "--porcelain"],
                        text=True,
                        stdout=__import__("subprocess").PIPE,
                        check=True,
                    ).stdout,
                    "",
                )
            finally:
                cleanup_worktree(context["source"], context["planning"], context["branch"])


if __name__ == "__main__":
    unittest.main()
