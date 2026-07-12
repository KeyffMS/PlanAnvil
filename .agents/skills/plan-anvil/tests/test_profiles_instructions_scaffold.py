from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from _helpers import cleanup_worktree, start_fixture

from common import load_json
from map_instructions import map_instructions
from validate_profile import validate_profile


class ProfileInstructionScaffoldTests(unittest.TestCase):
    def test_profile_scaffold_and_instruction_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = start_fixture(Path(tmp))
            try:
                self.assertTrue(validate_profile(context["planning"])["ok"])
                output = context["run_root"] / "evidence/instruction-map.json"
                result = map_instructions(
                    context["planning"],
                    affected_paths=["src/app.py", "tests/test_app.py"],
                    output=output,
                )
                self.assertTrue(result["ok"])
                data = load_json(output)
                self.assertEqual(data["files"][0]["path"], "AGENTS.md")
                self.assertTrue(data["files"][0]["full_read"])
                state = load_json(context["run_root"] / "state.json")
                self.assertEqual(state["status"], "INSTRUCTION_MAP_READY")
                local = context["run_root"] / "local-state.json"
                ignored = __import__("subprocess").run(
                    ["git", "-C", str(context["planning"]), "check-ignore", "-q", str(local.relative_to(context["planning"]))],
                    check=False,
                )
                self.assertEqual(ignored.returncode, 0)
            finally:
                cleanup_worktree(context["source"], context["planning"], context["branch"])

    def test_profile_detects_stale_hashed_instruction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = start_fixture(Path(tmp))
            try:
                self.assertTrue(validate_profile(context["planning"])["ok"])
                agents = context["planning"] / "AGENTS.md"
                agents.write_text(agents.read_text(encoding="utf-8") + "\nChanged after profiling.\n", encoding="utf-8")
                result = validate_profile(context["planning"])
                self.assertFalse(result["ok"])
                self.assertTrue(
                    any(item.get("kind") == "profile-evidence-stale" and item.get("path") == "AGENTS.md" for item in result["findings"]),
                    result["findings"],
                )
            finally:
                cleanup_worktree(context["source"], context["planning"], context["branch"])


if __name__ == "__main__":
    unittest.main()
