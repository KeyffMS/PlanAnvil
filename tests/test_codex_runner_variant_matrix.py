from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import codex_runner_variant_matrix as matrix

WORKFLOW = ROOT / ".github" / "workflows" / "plananvil-codex-runner-diagnostics.yml"
SOURCE = ROOT / "tools" / "codex_runner_variant_matrix.py"


class CodexRunnerVariantMatrixTests(unittest.TestCase):
    def test_exact_variant_matrix(self) -> None:
        self.assertEqual(
            matrix.VARIANT_NAMES,
            (
                "hook_json_bash_bypass",
                "hook_json_exec_command_bypass",
                "hook_toml_bash_bypass",
                "hook_json_bash_trusted_no_bypass",
                "hook_feature_disabled_control",
                "hook_json_bash_sidecar_env",
                "compact_body_after_prefix_no_budget_single",
                "compact_body_after_prefix_no_budget_two_step",
                "compact_body_after_prefix_budget_two_step",
                "compact_total_no_budget_two_step",
                "subagent_v1_explicit",
                "subagent_v2_explicit",
                "subagent_v1_default",
                "subagent_home_non_ephemeral",
            ),
        )

    def test_event_diagnostics_keeps_sanitized_errors_and_markers(self) -> None:
        stdout = "\n".join(
            [
                json.dumps({"type": "item.completed", "item": {"type": "command_execution", "text": "PLANANVIL_DIAG_HOOK_COMMAND_OK"}}),
                json.dumps({"type": "item.completed", "item": {"type": "error", "message": "failure under /home/runner/private"}}),
            ]
        )
        result = matrix._event_diagnostics(stdout)
        self.assertEqual(result["item_types"]["command_execution"], 1)
        self.assertEqual(result["item_types"]["error"], 1)
        self.assertTrue(any("PLANANVIL_DIAG_HOOK_COMMAND_OK" in value for value in result["diagnostic_markers"]))
        self.assertTrue(result["sanitized_errors"])
        self.assertNotIn("/home/runner", " ".join(result["sanitized_errors"]))

    def test_codex_args_are_noninteractive_sandboxed_and_network_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            args = matrix._codex_args(repo, "PLANANVIL_DIAG_TEST", hooks_enabled=True)
        joined = " ".join(args)
        self.assertIn("--ephemeral", args)
        self.assertIn("--ignore-user-config", args)
        self.assertIn("--dangerously-bypass-hook-trust", args)
        self.assertIn('approval_policy="never"', args)
        self.assertIn("sandbox_workspace_write.network_access=false", args)
        self.assertIn("features.hooks=true", args)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", joined)
        self.assertNotIn("danger-full-access", joined)
        self.assertNotIn("--privileged", joined)
        self.assertNotIn("SYS_ADMIN", joined)

    def test_json_and_toml_hook_fixtures_use_distinct_matchers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            json_repo = root / "json"
            matrix._init_repo(json_repo)
            matrix._seed_pretool(json_repo, matcher="^Bash$", representation="json")
            payload = json.loads((json_repo / ".codex" / "hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["hooks"]["PreToolUse"][0]["matcher"], "^Bash$")

            toml_repo = root / "toml"
            matrix._init_repo(toml_repo)
            matrix._seed_pretool(toml_repo, matcher="^Bash$", representation="toml")
            config = (toml_repo / ".codex" / "config.toml").read_text(encoding="utf-8")
            self.assertIn("[[hooks.PreToolUse]]", config)
            self.assertIn('matcher = "^Bash$"', config)
            self.assertIn("[[hooks.PreToolUse.hooks]]", config)

    def test_compaction_matrix_varies_scope_budget_and_followup(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('("compact_body_after_prefix_no_budget_single", "body_after_prefix", False, False)', source)
        self.assertIn('("compact_body_after_prefix_no_budget_two_step", "body_after_prefix", False, True)', source)
        self.assertIn('("compact_body_after_prefix_budget_two_step", "body_after_prefix", True, True)', source)
        self.assertIn('("compact_total_no_budget_two_step", "total", False, True)', source)
        self.assertIn("you MUST make a second separate shell tool call", source)
        self.assertIn("features.token_budget=", source)

    def test_subagent_matrix_varies_runtime_and_agent_type(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('("subagent_v1_explicit", False, True, False)', source)
        self.assertIn('("subagent_v2_explicit", True, True, False)', source)
        self.assertIn('("subagent_v1_default", False, False, False)', source)
        self.assertIn('("subagent_home_non_ephemeral", False, True, True)', source)
        self.assertIn("agent_type exactly `fixture_agent`", source)
        self.assertIn("features.multi_agent_v2=", source)
        self.assertIn("_prepare_isolated_codex_home", source)
        self.assertIn("_cleanup_isolated_codex_home", source)

    def test_workflow_is_main_only_self_hosted_and_diagnostic_only(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch", workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        for label in ("self-hosted", "linux", "x64", "plananvil", "codex"):
            self.assertIn(f"- {label}", workflow)
        self.assertIn("codex_runner_variant_matrix.py", workflow)
        self.assertIn("plananvil-codex-runner-diagnostics-${{ github.run_id }}", workflow)
        self.assertIn("Variant observations are intentionally non-gating", workflow)
        self.assertNotIn("release_gate_passed", workflow)
        self.assertNotIn("live_codex_qualification_harness_v6.py", workflow)

    def test_diagnostic_output_does_not_persist_raw_transcripts(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("sanitized_errors", source)
        self.assertIn("diagnostic_markers", source)
        self.assertIn("stderr_tail", source)
        self.assertNotIn('write_text(stdout', source)
        self.assertNotIn('write_text(stderr', source)
        self.assertIn("never a release gate", source)


if __name__ == "__main__":
    unittest.main()
