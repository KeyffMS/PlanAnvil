from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import codex_runner_precision_v2 as precision

SOURCE = ROOT / "tools" / "codex_runner_precision_v2.py"
PRODUCT_CONFIG = ROOT / ".codex" / "config.toml"


class CodexRunnerPrecisionV2Tests(unittest.TestCase):
    def test_exact_runtime_isolation_matrix(self) -> None:
        self.assertEqual(len(precision.VARIANT_NAMES), 11)
        self.assertEqual(
            precision.VARIANT_NAMES,
            (
                "project_cli_trust_ephemeral_deny",
                "project_persisted_trust_non_ephemeral_json_deny",
                "project_persisted_trust_non_ephemeral_toml_deny",
                "home_non_ephemeral_json_deny",
                "compact_home_body_after_prefix_single",
                "compact_home_body_after_prefix_two_step",
                "compact_home_total_two_step",
                "subagent_project_autodiscovery_non_ephemeral",
                "subagent_project_declared_non_ephemeral",
                "subagent_home_declared_non_ephemeral",
                "subagent_project_declared_ephemeral",
            ),
        )

    def test_hook_probe_distinguishes_discovery_from_pretool_match(self) -> None:
        source = precision._hook_script()
        self.assertNotIn("git rev-parse", source)
        self.assertIn('kind == "PreToolUse"', source)
        self.assertIn("cwd_matches_repo", source)
        self.assertIn("permissionDecisionReason", source)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text = precision._hooks_json(
                root / "hook.py", root / "hook.jsonl", root / "repo", decision="deny"
            )
        payload = json.loads(text)
        self.assertIn("SessionStart", payload["hooks"])
        self.assertEqual(payload["hooks"]["PreToolUse"][0]["matcher"], "^Bash$")

    def test_runtime_modes_separate_cli_and_persisted_trust(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            home = root / "home"
            repo.mkdir()
            home.mkdir()
            cli = precision._runtime_args(
                repo,
                "probe",
                home=home,
                ephemeral=True,
                cli_trust=True,
                ignore_user_config=True,
            )
            persisted = precision._runtime_args(
                repo,
                "probe",
                home=home,
                ephemeral=False,
                cli_trust=False,
            )
        self.assertIn("--strict-config", cli)
        self.assertIn("--ephemeral", cli)
        self.assertIn("--ignore-user-config", cli)
        self.assertTrue(any(value.startswith("projects.") for value in cli))
        self.assertNotIn("--ephemeral", persisted)
        self.assertNotIn("--ignore-user-config", persisted)
        self.assertIn('history.persistence="none"', persisted)

    def test_persisted_trust_uses_codex_projects_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            text = precision._project_trust_toml(repo)
        self.assertIn("[projects.", text)
        self.assertIn('trust_level = "trusted"', text)

    def test_compaction_home_control_proves_hook_engine_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = json.loads(
                precision._compact_hooks_json(
                    root / "compact.py", root / "compact.jsonl", root / "repo"
                )
            )
        self.assertIn("SessionStart", payload["hooks"])
        self.assertIn("PreCompact", payload["hooks"])
        self.assertIn("PostCompact", payload["hooks"])
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("features.token_budget=false", source)
        self.assertIn("second separate shell tool call", source)

    def test_subagent_matrix_compares_autodiscovery_declaration_and_ephemeral(self) -> None:
        auto = precision._project_agent_config(declared=False)
        declared = precision._project_agent_config(declared=True)
        self.assertNotIn("[agents.fixture_agent]", auto)
        self.assertIn("[agents.fixture_agent]", declared)
        self.assertIn('config_file = "./agents/fixture-agent.toml"', declared)
        token = "opaque-test-token"
        self.assertNotIn(token, precision._agent_toml())
        self.assertIn(token, precision._subagent_script(token))

    def test_product_roles_are_explicitly_declared(self) -> None:
        config = PRODUCT_CONFIG.read_text(encoding="utf-8")
        self.assertIn("[agents.plan_anvil_profiler]", config)
        self.assertIn('config_file = "./agents/plan-anvil-profiler.toml"', config)
        self.assertIn("[agents.plan_anvil_reviewer]", config)
        self.assertIn('config_file = "./agents/plan-anvil-reviewer.toml"', config)

    def test_one_failure_does_not_abort_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            result = precision._run_case(
                "synthetic",
                lambda: (_ for _ in ()).throw(RuntimeError("boom")),
                output,
            )
            self.assertEqual(result["diagnostic_status"], "HARNESS_ERROR")
            self.assertTrue((output / "synthetic.json").is_file())

    def test_dispatches_all_eleven_without_codex(self) -> None:
        def fake(name: str) -> dict[str, object]:
            return {"variant": name, "returncode": 0, "diagnostic_status": "TEST"}

        def hook(_root: Path, _output: Path, name: str, **_kwargs: object):
            return fake(name)

        def compact(_root: Path, _output: Path, name: str, **_kwargs: object):
            return fake(name)

        def subagent(_root: Path, _output: Path, name: str, **_kwargs: object):
            return fake(name)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runtime"
            output = Path(tmp) / "artifact"
            with (
                mock.patch.object(precision, "_hook_variant", side_effect=hook) as h,
                mock.patch.object(precision, "_compact_variant", side_effect=compact) as c,
                mock.patch.object(precision, "_subagent_variant", side_effect=subagent) as s,
            ):
                results = precision.run_matrix(root, output)
            self.assertEqual([item["variant"] for item in results], list(precision.VARIANT_NAMES))
            self.assertEqual((h.call_count, c.call_count, s.call_count), (4, 3, 4))
            self.assertEqual(len(list(output.glob("*.json"))), 11)

    def test_evidence_does_not_persist_raw_transcripts(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("write_text(stdout", source)
        self.assertNotIn("write_text(stderr", source)
        self.assertIn("opaque_token_persisted_in_evidence", source)
        self.assertIn("never a release gate", source)


if __name__ == "__main__":
    unittest.main()
