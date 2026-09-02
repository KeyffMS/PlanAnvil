from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "live_codex_qualification_harness_v5.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "plananvil-codex-qualification.yml"
RUNBOOK_PATH = ROOT / "docs" / "CODEX_SANDBOX_RUNBOOK.md"


class LiveCodexHarnessV5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = MODULE_PATH.read_text(encoding="utf-8")
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        cls.runbook = RUNBOOK_PATH.read_text(encoding="utf-8")

    def test_exact_target_capability_and_inheritance(self) -> None:
        self.assertIn('TARGET_CAPABILITIES = {"C13"}', self.source)
        self.assertIn("_ORIGINAL_CAPABILITY_RUNTIME = prior.capability_runtime", self.source)
        self.assertIn("import live_codex_qualification_harness_v4 as prior", self.source)

    def test_ephemeral_first_and_known_error_gated_fallback(self) -> None:
        self.assertIn("KNOWN_PARENT_THREAD_FAILURE_RE", self.source)
        self.assertIn("collab\\s+spawn\\s+failed", self.source)
        self.assertIn("known_e and ALLOW_NON_EPHEMERAL_FALLBACK", self.source)
        self.assertIn('transport="ephemeral"', self.source)
        self.assertIn('transport="non-ephemeral"', self.source)
        self.assertIn("ephemeral_known_transport_blocker_fallback_not_enabled", self.source)

    def test_context_proof_is_not_exposed_to_root_prompt(self) -> None:
        self.assertIn("_context_proof(source_commit)", self.source)
        self.assertIn("Never invent or guess the opaque value", self.source)
        self.assertIn("secret_value_retained_in_evidence", self.source)
        self.assertNotIn("FIXTURE_SUBAGENT_CONTEXT", self.source)

    def test_real_hook_and_continue_false_are_required(self) -> None:
        self.assertIn('"matcher": "^fixture_agent$"', self.source)
        self.assertIn('"hookEventName": "SubagentStart"', self.source)
        self.assertIn('"continue": False', self.source)
        self.assertIn("hook_continue_false", self.source)
        self.assertIn("hook_additional_context", self.source)
        self.assertIn("subagent_start_hook_events", self.source)

    def test_non_ephemeral_home_is_isolated_without_copying_auth(self) -> None:
        self.assertIn('os.symlink(str(original_auth), str(home / "auth.json"))', self.source)
        self.assertNotIn("shutil.copy2(original_auth", self.source)
        self.assertNotIn("read_bytes()", self.source)
        self.assertIn('history.persistence="none"', self.source)
        self.assertIn("sqlite_home=", self.source)
        self.assertIn("log_dir=", self.source)
        self.assertIn("session_cleanup_verified", self.source)
        self.assertIn("auth_metadata_unchanged", self.source)

    def test_v5_historical_controller_remains_diagnostic_only(self) -> None:
        self.assertIn(
            "C13 non-ephemeral fallback is diagnostic-only until the baseline contract is updated",
            self.source,
        )
        self.assertIn("--allow-c13-non-ephemeral-fallback", self.source)
        self.assertIn("--only", self.source)

    def test_safety_boundary_is_not_weakened(self) -> None:
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", self.source)
        self.assertNotIn("danger-full-access", self.source)
        self.assertNotIn("--privileged", self.source)
        self.assertNotIn("SYS_ADMIN", self.source)
        self.assertIn('sandbox="read-only"', self.source)
        self.assertIn("completed_command_items", self.source)
        self.assertIn("completed_file_change_items", self.source)
        self.assertIn("repository_unchanged", self.source)

    def test_current_workflow_uses_v6_and_keeps_c13_short_mode(self) -> None:
        self.assertIn("- c13", self.workflow)
        self.assertIn("inputs.mode == 'c13'", self.workflow)
        self.assertIn("python3 tools/live_codex_qualification_harness_v6.py", self.workflow)
        self.assertIn("--only C13", self.workflow)
        self.assertIn("--allow-c13-non-ephemeral-fallback", self.workflow)
        self.assertIn("inputs.mode == 'full'", self.workflow)

    def test_runbook_documents_baseline23_full_transport(self) -> None:
        self.assertIn("`c13`", self.runbook)
        self.assertIn("baseline 2.3", self.runbook.lower())
        self.assertIn("home-scoped", self.runbook)
        self.assertIn("project-scoped", self.runbook)
        self.assertIn("mode=full", self.runbook)


if __name__ == "__main__":
    unittest.main()
