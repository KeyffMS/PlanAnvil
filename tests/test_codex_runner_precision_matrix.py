from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import codex_runner_precision_matrix as matrix

WORKFLOW = ROOT / ".github" / "workflows" / "plananvil-codex-qualification.yml"
SOURCE = ROOT / "tools" / "codex_runner_precision_matrix.py"


class CodexRunnerPrecisionMatrixTests(unittest.TestCase):
    def test_exact_precision_variants(self) -> None:
        self.assertEqual(len(matrix.VARIANT_NAMES), 11)
        self.assertEqual(matrix.VARIANT_NAMES[0], "pretool_json_bash_allow_absolute")
        self.assertIn("compact_body_after_prefix_two_step_absolute", matrix.VARIANT_NAMES)
        self.assertIn("subagent_non_ephemeral_project_explicit", matrix.VARIANT_NAMES)
        self.assertIn("subagent_non_ephemeral_home_explicit", matrix.VARIANT_NAMES)

    def test_pretool_probe_has_absolute_recorder_and_real_deny(self) -> None:
        source = matrix._pretool_script()
        self.assertNotIn("git rev-parse", source)
        self.assertIn("Path(sys.argv[1])", source)
        self.assertIn("cwd_matches_repo", source)
        self.assertIn("permissionDecisionReason", source)
        self.assertIn("PLANANVIL_DIAG_PRETOOL_DENY", source)

    def test_compaction_probe_has_absolute_recorder(self) -> None:
        source = matrix._compact_script()
        self.assertNotIn("git rev-parse", source)
        self.assertIn("Path(sys.argv[2])", source)
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("features.token_budget=false", text)
        self.assertIn("you MUST make a second separate shell tool call", text)
        self.assertIn("compact_body_after_prefix_single_absolute", text)
        self.assertIn("compact_total_two_step_absolute", text)

    def test_subagent_opaque_value_is_not_present_in_agent_config(self) -> None:
        token = "opaque-test-value"
        self.assertNotIn(token, matrix._agent_toml())
        self.assertIn(token, matrix._subagent_script(token))
        self.assertNotIn("git rev-parse", matrix._subagent_script(token))
        self.assertIn("PLANANVIL_DIAG_CONTEXT_TOKEN=", matrix._agent_toml())

    def test_command_observation_uses_aggregated_output_not_command_string(self) -> None:
        marker = "PLANANVIL_DIAG_HOOK_COMMAND_OK"
        denied = json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "command": f"printf {marker}",
                    "aggregated_output": "blocked",
                    "status": "failed",
                    "exit_code": 1,
                },
            }
        )
        observed = matrix._command_observation(denied, marker)
        self.assertFalse(observed["marker_output_observed"])
        self.assertEqual(observed["failed_count"], 1)

    def test_secret_redaction_is_recursive(self) -> None:
        token = "secret-context"
        value = {"a": [f"prefix-{token}", {"b": token}]}
        serialized = json.dumps(matrix._redact(value, token), sort_keys=True)
        self.assertNotIn(token, serialized)
        self.assertIn("<context-token>", serialized)

    def test_one_variant_failure_does_not_abort_artifact_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            result = matrix._run_case(
                "synthetic",
                lambda: (_ for _ in ()).throw(TypeError("boom")),
                output,
            )
            self.assertEqual(result["diagnostic_status"], "HARNESS_ERROR")
            self.assertTrue((output / "synthetic.json").is_file())

    def test_run_matrix_dispatches_all_variants_without_codex(self) -> None:
        def fake(name: str) -> dict[str, object]:
            return {"variant": name, "returncode": 0, "diagnostic_status": "TEST"}

        def hook(_root: Path, _output: Path, name: str, *_args: object) -> dict[str, object]:
            return fake(name)

        def compact(_root: Path, _output: Path, name: str, *_args: object) -> dict[str, object]:
            return fake(name)

        def subagent(_root: Path, _output: Path, name: str, *_args: object) -> dict[str, object]:
            return fake(name)

        with tempfile.TemporaryDirectory() as tmp:
            root, output = Path(tmp) / "runtime", Path(tmp) / "artifact"
            with (
                mock.patch.object(matrix, "_hook_variant", side_effect=hook) as hook_mock,
                mock.patch.object(matrix, "_compact_variant", side_effect=compact) as compact_mock,
                mock.patch.object(matrix, "_subagent_variant", side_effect=subagent) as subagent_mock,
            ):
                results = matrix.run_matrix(root, output)
            self.assertEqual([item["variant"] for item in results], list(matrix.VARIANT_NAMES))
            self.assertEqual((hook_mock.call_count, compact_mock.call_count, subagent_mock.call_count), (5, 3, 3))
            self.assertEqual(len(list(output.glob("*.json"))), 11)

    def test_precision_mode_uses_existing_runner_allowed_workflow(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("- precision", workflow)
        self.assertIn("inputs.mode == 'precision'", workflow)
        precision_job = workflow[workflow.index("  precision:"):workflow.index("  full:")]
        self.assertIn("codex_runner_precision_v2.py", precision_job)
        for label in ("self-hosted", "linux", "x64", "plananvil", "codex"):
            self.assertIn(f"- {label}", precision_job)
        self.assertIn("Variant observations are intentionally non-gating", precision_job)
        self.assertNotIn("live_codex_qualification_harness_v6.py", precision_job)

    def test_precision_artifact_never_persists_raw_transcripts_or_hook_scripts(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("write_text(stdout", source)
        self.assertNotIn("write_text(stderr", source)
        self.assertIn('root / "scripts"', source)
        self.assertIn("not uploaded", source)
        self.assertIn("never a release gate", source)


if __name__ == "__main__":
    unittest.main()
