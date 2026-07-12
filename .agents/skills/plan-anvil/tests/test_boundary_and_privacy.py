from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from _helpers import author_valid_plan, cleanup_worktree, start_fixture

from map_instructions import map_instructions
from validate_plan import validate_plan


class BoundaryAndPrivacyTests(unittest.TestCase):
    def test_generator_executor_boundary_violation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = start_fixture(Path(tmp))
            try:
                map_instructions(
                    context["planning"],
                    affected_paths=["src/app.py"],
                    output=context["run_root"] / "evidence/instruction-map.json",
                )
                author_valid_plan(context)
                plan = context["run_root"] / "PLAN.md"
                plan.write_text(
                    plan.read_text(encoding="utf-8")
                    + "\nAfter generating the plan, immediately start Jim and implement STAGE-01.\n",
                    encoding="utf-8",
                    newline="\n",
                )
                result = validate_plan(context["planning"], context["run_root"])
                self.assertFalse(result["ok"])
                self.assertTrue(
                    any(item["kind"] == "generator-executor-boundary-violation" for item in result["findings"]),
                    result,
                )
            finally:
                cleanup_worktree(context["source"], context["planning"], context["branch"])


if __name__ == "__main__":
    unittest.main()
