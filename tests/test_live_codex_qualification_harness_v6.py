from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "live_codex_qualification_harness_v6.py"
COMPAT_PATH = ROOT / "tools" / "live_codex_qualification_codex0152.py"
REGRESSION_PATH = ROOT / "tools" / "live_codex_qualification_regression.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "plananvil-codex-qualification.yml"
BASELINE_PATH = ROOT / "docs" / "CODEX_CAPABILITY_BASELINE.md"
RUNBOOK_PATH = ROOT / "docs" / "CODEX_SANDBOX_RUNBOOK.md"


class LiveCodexHarnessV6Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = MODULE_PATH.read_text(encoding="utf-8")
        cls.compat = COMPAT_PATH.read_text(encoding="utf-8")
        cls.regression = REGRESSION_PATH.read_text(encoding="utf-8")
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        cls.baseline = BASELINE_PATH.read_text(encoding="utf-8")
        cls.runbook = RUNBOOK_PATH.read_text(encoding="utf-8")

    def test_v6_consolidates_exact_codex0152_targets(self) -> None:
        self.assertIn("import live_codex_qualification_codex0152 as compat", self.source)
        self.assertIn("TARGET_CAPABILITIES = compat.TARGET_CAPABILITIES", self.source)
        self.assertIn("TARGET_CAPABILITIES = regression.TARGET_CAPABILITIES", self.compat)
        self.assertIn('TARGET_CAPABILITIES = {"C03", "C06", "C08", "C09", "C13", "C16"}', self.regression)
        self.assertIn("_ORIGINAL_CAPABILITY_RUNTIME = prior.capability_runtime", self.source)
        for capability_id in ("C03", "C06", "C08", "C09", "C13"):
            self.assertIn(f'if capability_id == "{capability_id}"', self.source)
        self.assertIn("return compat.run_c16(**common)", self.source)

    def test_agent_identity_is_aligned(self) -> None:
        self.assertIn('HOME_AGENT_NAME = "fixture_agent"', self.source)
        self.assertIn('HOME_AGENT_FILENAME = "fixture_agent.toml"', self.source)
        self.assertIn('"matcher": f"^{HOME_AGENT_NAME}$"', self.source)
        self.assertIn("agent_name_matches_filename", self.source)
        self.assertIn("required_spawn_agent_type", self.source)
        self.assertIn("agent_type` exactly `fixture_agent`", self.compat)

    def test_ephemeral_attempt_remains_project_scoped(self) -> None:
        self.assertIn("_seed_project_fixture(project_repo, proof, include_project_agent=True)", self.source)
        self.assertIn("ephemeral=True", self.source)
        self.assertIn('trial_e["agent_fixture_scope"] = "project"', self.source)

    def test_fallback_separates_agent_discovery_from_project_hook(self) -> None:
        self.assertIn("_seed_project_fixture(fallback_repo, proof, include_project_agent=False)", self.source)
        self.assertIn('home / "agents" / HOME_AGENT_FILENAME', self.source)
        self.assertIn('trial_n["agent_fixture_scope"] = "disposable_CODEX_HOME"', self.source)
        self.assertIn('trial_n["project_agent_present"] = False', self.source)
        self.assertIn('trial_n["project_scoped_subagent_start_hook"] = True', self.source)
        self.assertIn("compat.run_c13(_c13_runtime", self.source)

    def test_fallback_is_still_known_error_gated(self) -> None:
        self.assertIn("known_e and ALLOW_NON_EPHEMERAL_FALLBACK", self.source)
        self.assertIn("ephemeral_known_transport_blocker_fallback_not_enabled", self.source)
        self.assertIn("non_ephemeral_home_agent_fallback", self.source)

    def test_non_ephemeral_cleanup_and_auth_invariants_remain_required(self) -> None:
        self.assertIn("prior._prepare_isolated_codex_home", self.source)
        self.assertIn("prior._cleanup_isolated_codex_home", self.source)
        self.assertIn("session_cleanup_verified", self.source)
        self.assertIn("auth_metadata_unchanged", self.source)
        self.assertIn("home_scoped_fixture_agent_materialized", self.source)

    def test_full_workflow_stays_on_v6_and_enables_baseline23_fallback(self) -> None:
        self.assertIn("python3 tools/live_codex_qualification_harness_v6.py", self.workflow)
        self.assertIn("qualification_args=(--allow-c13-non-ephemeral-fallback)", self.workflow)
        self.assertIn("--only C13", self.workflow)
        self.assertIn("inputs.mode == 'full'", self.workflow)

    def test_baseline_and_runbook_remain_23(self) -> None:
        self.assertIn("Baseline version:** 2.3", self.baseline)
        self.assertIn("ephemeral-first", self.baseline)
        self.assertIn("home-scoped", self.baseline)
        self.assertIn("baseline 2.3", self.runbook.lower())
        self.assertIn("CODEX_HOME/agents/fixture_agent.toml", self.runbook)
        self.assertIn("project-scoped", self.runbook)

    def test_safety_boundary_is_not_weakened(self) -> None:
        combined = self.source + "\n" + self.compat + "\n" + self.regression
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", combined)
        self.assertNotIn("danger-full-access", combined)
        self.assertNotIn("--privileged", combined)
        self.assertNotIn("SYS_ADMIN", combined)
        self.assertIn('sandbox_mode = "read-only"', self.source)
        self.assertIn("base.git_snapshot", combined)


if __name__ == "__main__":
    unittest.main()
