from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "live_codex_qualification_harness_v4.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "plananvil-codex-qualification.yml"


class LiveCodexHarnessV4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = MODULE_PATH.read_text(encoding="utf-8")
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_exact_target_capabilities(self) -> None:
        self.assertIn('TARGET_CAPABILITIES = {"C06", "C08", "C09"}', self.source)
        self.assertIn("_ORIGINAL_CAPABILITY_RUNTIME = prior.capability_runtime", self.source)

    def test_c06_uses_real_pretooluse_hook_and_outer_postcondition(self) -> None:
        self.assertIn('"PreToolUse": "plan-anvil-guard.py"', self.source)
        self.assertIn('item.get("tool_name") == "apply_patch"', self.source)
        self.assertIn("outer_non_intercepted_postcondition", self.source)
        self.assertIn("git_postcondition_detected", self.source)
        self.assertIn("mutation_origin=outer qualification harness outside Codex hook lifecycle", self.source)

    def test_c08_uses_real_auto_compact_stop_and_repair(self) -> None:
        self.assertIn("C08_COMPACT_LIMIT = 200", self.source)
        self.assertIn('COMPACT_SCOPE = "body_after_prefix"', self.source)
        self.assertIn('"PreCompact": "plan-anvil-compaction.py"', self.source)
        self.assertIn("automatic_compaction_without_valid_checkpoint", self.source)
        self.assertIn("automatic_compaction_after_checkpoint_repair", self.source)
        self.assertIn("stop_reason_mentions_checkpoint", self.source)
        self.assertIn("_create_checkpoint(planning=planning, run_root=run_root)", self.source)

    def test_c09_requires_two_real_compactions_and_continuation(self) -> None:
        self.assertIn("C09_COMPACT_LIMIT = 1000", self.source)
        self.assertIn("len(pre) >= 2 and len(post) >= 2", self.source)
        self.assertIn("_continued_after_second_postcompact", self.source)
        self.assertIn("tool_use_after_second_postcompact", self.source)
        self.assertIn("checkpoint_after_valid", self.source)

    def test_compact_limit_is_redundantly_applied_at_runtime(self) -> None:
        self.assertIn("model_auto_compact_token_limit={compact_limit}", self.source)
        self.assertIn('model_auto_compact_token_limit_scope="{compact_scope or COMPACT_SCOPE}"', self.source)
        self.assertIn('model_auto_compact_token_limit_scope = "{scope}"', self.source)

    def test_safety_boundary_is_not_weakened(self) -> None:
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", self.source)
        self.assertNotIn("danger-full-access", self.source)
        self.assertNotIn("--privileged", self.source)
        self.assertNotIn("SYS_ADMIN", self.source)
        self.assertIn('sandbox="read-only"', self.source)
        self.assertIn('sandbox="workspace-write"', self.source)

    def test_v4_is_chained_under_current_v6_wrapper(self) -> None:
        v5 = (ROOT / "tools" / "live_codex_qualification_harness_v5.py").read_text(
            encoding="utf-8"
        )
        v6 = (ROOT / "tools" / "live_codex_qualification_harness_v6.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("import live_codex_qualification_harness_v4 as prior", v5)
        self.assertIn("import live_codex_qualification_harness_v5 as prior", v6)
        self.assertIn("python3 tools/live_codex_qualification_harness_v6.py", self.workflow)


if __name__ == "__main__":
    unittest.main()
