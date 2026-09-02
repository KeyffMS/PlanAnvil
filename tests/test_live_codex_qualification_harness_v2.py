from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "live_codex_qualification_harness_v2.py"


class LiveCodexHarnessV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = MODULE_PATH.read_text(encoding="utf-8")

    def test_wrapper_compiles(self) -> None:
        compile(self.source, str(MODULE_PATH), "exec")

    def test_exact_target_capabilities(self) -> None:
        for capability in ["C02", "C09", "C11", "C13", "C14", "C16"]:
            self.assertIn(f'"{capability}"', self.source)
        self.assertIn("_ORIGINAL_CAPABILITY_RUNTIME = prior.capability_runtime", self.source)

    def test_c02_installs_explicit_only_repository_skill(self) -> None:
        self.assertIn("allow_implicit_invocation: false", self.source)
        self.assertIn("FIXTURE_SKILL_ACTIVE", self.source)
        self.assertIn("implicit_activation_disabled", self.source)
        self.assertIn("explicit_activation_available", self.source)

    def test_c09_and_c14_disable_python_bytecode(self) -> None:
        self.assertIn('os.environ["PYTHONDONTWRITEBYTECODE"] = "1"', self.source)
        self.assertIn("return prior._c09_runtime(**common)", self.source)
        self.assertIn("return prior._c14_runtime(**common)", self.source)

    def test_c11_records_current_docs_and_outer_mapping(self) -> None:
        self.assertIn("https://learn.chatgpt.com/docs/agent-configuration/agents-md", self.source)
        self.assertIn("AGENTS.override.md", self.source)
        self.assertIn("root_to_nested_order_matches", self.source)
        self.assertIn("nested_agents_ignored_when_override_exists", self.source)

    def test_c13_uses_project_scoped_real_subagent_hook(self) -> None:
        self.assertIn("SubagentStart", self.source)
        self.assertIn("FIXTURE_SUBAGENT_CONTEXT", self.source)
        self.assertIn('"continue": False', self.source)
        self.assertIn("CHILD_STARTED_WITH_CONTEXT", self.source)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", self.source)

    def test_c16_exercises_real_success_signing_and_hook_diagnostics(self) -> None:
        self.assertIn("GIT_READY", self.source)
        self.assertIn("GIT_SIGNING_BLOCKED", self.source)
        self.assertIn("GIT_HOOK_BLOCKED", self.source)
        self.assertIn("pre-commit hook failed: C16 fixture hook rejection", self.source)
        self.assertIn("gpg: signing failed: C16 fixture signing failure", self.source)
        self.assertIn("cleanup_errors is empty", self.source)


if __name__ == "__main__":
    unittest.main()
