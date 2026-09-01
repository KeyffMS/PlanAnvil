from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "live_codex_qualification_harness.py"
sys.path.insert(0, str(ROOT / "tools"))
SPEC = importlib.util.spec_from_file_location("live_codex_qualification_harness", MODULE_PATH)
assert SPEC and SPEC.loader
harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(harness)


class LiveCodexHarnessOverrideTests(unittest.TestCase):
    def test_only_known_harness_failures_are_overridden(self) -> None:
        self.assertEqual(harness.TARGET_CAPABILITIES, {"C01", "C05", "C09", "C14"})

    def test_c01_seeds_repository_skill_and_nested_start(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("fixture-capability", source)
        self.assertIn("FIXTURE_SKILL_ACTIVE", source)
        self.assertIn("nested_working_directory_discovery", source)
        self.assertIn("cwd=nested", source)

    def test_c05_has_explicit_stale_bundle_trial(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("stale_bundle_rejected", source)
        self.assertIn("Modify PLAN.md without changing", source)
        self.assertIn("review-bundle.sha256", source)
        self.assertIn("changed_bundle_rejected", source)
        self.assertIn("missing_bundle_rejected", source)
        self.assertIn("escaped_bundle_rejected", source)

    def test_c09_uses_genuine_auto_compaction_and_real_hooks(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("model_auto_compact_token_limit = 5000", source)
        self.assertIn("qualification-hook-proxy.py", source)
        self.assertIn("PreCompact", source)
        self.assertIn("PostCompact", source)
        self.assertIn("create_generation_checkpoint.py", source)
        self.assertIn("Do NOT invoke hook scripts directly", source)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", source)
        self.assertNotIn("danger-full-access", source)

    def test_c14_uses_explicit_auxiliary_writable_git_root(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn('source = worktrees / "source"', source)
        self.assertIn("../worktrees/source", source)
        self.assertIn("../worktrees/planning", source)
        self.assertIn("plananvil_dist.py", source)
        self.assertIn("outer_planning_worktree_exists", source)


if __name__ == "__main__":
    unittest.main()
