from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from _helpers import cleanup_worktree, start_fixture

from common import atomic_write_json, load_json
from map_instructions import map_instructions
from schema_validator import validate_file


class InstructionConflictsAndExamplesTests(unittest.TestCase):
    def test_unresolved_critical_instruction_conflict_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = start_fixture(root)
            try:
                nested = context["planning"] / "src/AGENTS.md"
                nested.write_text("# Nested instructions\n\nNever change validation behavior.\n", encoding="utf-8")
                # The file is planning evidence only for this test and is not committed.
                conflicts = root / "conflicts.json"
                atomic_write_json(
                    conflicts,
                    [
                        {
                            "paths": ["AGENTS.md", "src/AGENTS.md"],
                            "critical": True,
                            "resolution": None,
                        }
                    ],
                )
                result = map_instructions(
                    context["planning"],
                    affected_paths=["src/app.py"],
                    output=context["run_root"] / "evidence/instruction-map.json",
                    conflicts_file=conflicts,
                )
                self.assertFalse(result["ok"])
                self.assertEqual(result["result"], "BLOCKED_BY_INSTRUCTION_CONFLICT")
                state = load_json(context["run_root"] / "state.json")
                self.assertEqual(state["status"], "BLOCKED")
                self.assertIn("BLOCKED_BY_INSTRUCTION_CONFLICT", state["open_blockers"])
            finally:
                cleanup_worktree(context["source"], context["planning"], context["branch"])

    def test_golden_example_machine_artifacts_match_schemas(self) -> None:
        repository = Path(__file__).resolve().parents[4]
        schemas = repository / ".agents/skills/plan-anvil/schemas"
        checks: list[tuple[Path, Path]] = []
        for name in ["small-change", "stateful-change", "blocked-plan"]:
            run = repository / "examples" / name / "run"
            checks.extend(
                [
                    (run / "manifest.json", schemas / "manifest.schema.json"),
                    (run / "state.json", schemas / "state.schema.json"),
                    (run / "compliance.json", schemas / "compliance.schema.json"),
                    (run / "traceability.json", schemas / "traceability.schema.json"),
                    (run / "evidence/analysis.json", schemas / "analysis.schema.json"),
                    (run / "evidence/git-capability.json", schemas / "git-capability.schema.json"),
                    (run / "evidence/lifecycle.json", schemas / "lifecycle.schema.json"),
                ]
            )
            checks.extend((path, schemas / "risk.schema.json") for path in (run / "risks").glob("RISK-*.json"))
            if (run / "reports/plan-review/blind-review.json").exists():
                checks.append((run / "reports/plan-review/blind-review.json", schemas / "review.schema.json"))
                checks.append((run / "reports/plan-review/comparison.json", schemas / "comparison.schema.json"))
        failures = {str(path): validate_file(path, schema) for path, schema in checks if validate_file(path, schema)}
        self.assertEqual(failures, {})
        restricted = repository / "examples/git-write-restricted"
        self.assertFalse((restricted / "PLAN.md").exists())
        self.assertFalse((restricted / "SYSTEM_PROFILE.md").exists())


if __name__ == "__main__":
    unittest.main()
