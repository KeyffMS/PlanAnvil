from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import live_codex_qualification_harness_v7 as v7

WORKFLOW = ROOT / ".github" / "workflows" / "plananvil-codex-qualification.yml"
SOURCE = ROOT / "tools" / "live_codex_qualification_harness_v7.py"


class LiveCodexHarnessV7Tests(unittest.TestCase):
    def test_full_workflow_uses_v7(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        full = workflow[workflow.index("  full:"):]
        self.assertIn("python3 tools/live_codex_qualification_harness_v7.py", full)
        self.assertNotIn("python3 tools/live_codex_qualification_harness_v6.py", full)

    def test_live_runner_trust_restores_config_and_keeps_real_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            repo = root / "repo"
            home.mkdir()
            repo.mkdir()
            config = home / "config.toml"
            original = b'model = "fixture"\n'
            config.write_bytes(original)
            observed: list[dict[str, object]] = []

            def fake_common(**kwargs: object) -> list[str]:
                observed.append(dict(kwargs))
                return ["codex", "exec", "--ignore-user-config"]

            previous = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = str(home)
            try:
                with (
                    mock.patch.object(v7, "_runner_codex_home", return_value=home),
                    mock.patch.object(v7.base, "common_codex_args", side_effect=fake_common),
                ):
                    with v7._live_runner_persisted_trust_runtime():
                        args = v7.base.common_codex_args(cwd=repo, trust_project=True)
                        text = config.read_text(encoding="utf-8")
                        self.assertIn("[projects.", text)
                        self.assertIn('trust_level = "trusted"', text)
                        self.assertEqual(os.environ.get("CODEX_HOME"), str(home))
                        self.assertNotIn("--ignore-user-config", args)
                self.assertEqual(config.read_bytes(), original)
            finally:
                if previous is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous

            self.assertEqual(len(observed), 1)
            self.assertIs(observed[0]["trust_project"], False)

    def test_c08_c09_use_live_auth_runtime(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("def run_c08", source)
        self.assertIn("def run_c09", source)
        self.assertGreaterEqual(source.count("_live_runner_persisted_trust_runtime()"), 2)
        self.assertIn("change only config.toml", source)

    def test_c13_fallback_keeps_role_and_hook_project_scoped(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("_seed_declared_project_fixture(fallback_repo, proof)", source)
        self.assertIn('trial_n["project_agent_present"] = True', source)
        self.assertIn('trial_n["project_scoped_subagent_start_hook"] = True', source)
        self.assertIn('trial_n["home_agent_materialized"] = False', source)
        self.assertNotIn("_prepare_home_scoped_fallback_agent", source)

    def test_project_fixture_declares_exact_agent_role(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)

            def seed(target: Path, _proof: str, *, include_project_agent: bool) -> None:
                self.assertTrue(include_project_agent)
                (target / ".codex" / "agents").mkdir(parents=True)
                (target / ".codex" / "config.toml").write_text(
                    "[agents]\nenabled = true\n", encoding="utf-8"
                )
                (target / ".codex" / "agents" / v7.v6.HOME_AGENT_FILENAME).write_text(
                    'name = "fixture_agent"\n', encoding="utf-8"
                )

            with mock.patch.object(v7.v6, "_seed_project_fixture", side_effect=seed):
                materialized = v7._seed_declared_project_fixture(repo, "opaque")
            config = (repo / ".codex" / "config.toml").read_text(encoding="utf-8")
            self.assertTrue(materialized)
            self.assertIn("[agents.fixture_agent]", config)
            self.assertIn('config_file = "./agents/fixture_agent.toml"', config)

    def test_safety_boundaries_are_not_weakened(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", source)
        self.assertNotIn("danger-full-access", source)
        self.assertNotIn("--privileged", source)
        self.assertNotIn("SYS_ADMIN", source)


if __name__ == "__main__":
    unittest.main()
