from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import live_codex_qualification_codex0152 as compat


class Codex0152PersistedTrustTests(unittest.TestCase):
    def test_persisted_trust_file_is_idempotent_and_enables_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            repo = root / "repo"
            repo.mkdir()

            compat._write_persisted_project_trust(home, repo)
            compat._write_persisted_project_trust(home, repo)

            text = (home / "config.toml").read_text(encoding="utf-8")
            header = f"[projects.{compat.base.toml_quote(str(repo.resolve()))}]"
            self.assertIn("[features]", text)
            self.assertIn("hooks = true", text)
            self.assertEqual(text.count(header), 1)
            self.assertIn('trust_level = "trusted"', text)

    def test_persisted_trust_args_remove_invalid_cli_trust_and_load_user_config(self) -> None:
        original = compat.base.common_codex_args
        calls: list[dict[str, object]] = []

        def fake_common(**kwargs: object) -> list[str]:
            calls.append(dict(kwargs))
            args = ["codex", "exec", "--ignore-user-config"]
            if kwargs.get("trust_project"):
                args += ["-c", 'projects."/tmp/repo".trust_level="trusted"']
            return args

        compat.base.common_codex_args = fake_common
        try:
            with compat._persisted_trust_args():
                args = compat.base.common_codex_args(
                    cwd=Path("/tmp/repo"),
                    sandbox="read-only",
                    schema=Path("schema.json"),
                    output=Path("output.json"),
                    trust_project=True,
                )
        finally:
            compat.base.common_codex_args = original

        self.assertFalse(bool(calls[-1]["trust_project"]))
        self.assertNotIn("--ignore-user-config", args)
        self.assertFalse(any("projects." in item for item in args))

    def test_isolated_runtime_persists_each_probed_cwd_and_restores_environment(self) -> None:
        original_common = compat.base.common_codex_args
        previous_home = os.environ.get("CODEX_HOME")

        def fake_common(**kwargs: object) -> list[str]:
            args = ["codex", "exec", "--ignore-user-config"]
            if kwargs.get("trust_project"):
                args += ["-c", 'projects."bad".trust_level="trusted"']
            return args

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cap_runtime = root / "runtime"
            home = root / "isolated-home"
            repo_a = root / "repo-a"
            repo_b = root / "repo-b"
            home.mkdir()
            repo_a.mkdir()
            repo_b.mkdir()

            compat.base.common_codex_args = fake_common
            try:
                with (
                    mock.patch.object(
                        compat.v5,
                        "_prepare_isolated_codex_home",
                        return_value=(home, None, None),
                    ),
                    mock.patch.object(
                        compat.v5,
                        "_cleanup_isolated_codex_home",
                        return_value=(True, True),
                    ) as cleanup,
                    compat._isolated_persisted_trust_runtime(cap_runtime),
                ):
                    self.assertEqual(os.environ.get("CODEX_HOME"), str(home))
                    args_a = compat.base.common_codex_args(
                        cwd=repo_a,
                        sandbox="read-only",
                        schema=Path("schema.json"),
                        output=Path("output.json"),
                        trust_project=True,
                    )
                    args_b = compat.base.common_codex_args(
                        cwd=repo_b,
                        sandbox="read-only",
                        schema=Path("schema.json"),
                        output=Path("output.json"),
                        trust_project=True,
                    )

                cleanup.assert_called_once_with(home, None, None)
            finally:
                compat.base.common_codex_args = original_common

            text = (home / "config.toml").read_text(encoding="utf-8")
            self.assertIn(str(repo_a.resolve()), text)
            self.assertIn(str(repo_b.resolve()), text)
            self.assertNotIn("--ignore-user-config", args_a)
            self.assertNotIn("--ignore-user-config", args_b)
            self.assertFalse(any("projects." in item for item in args_a + args_b))

        self.assertEqual(os.environ.get("CODEX_HOME"), previous_home)


if __name__ == "__main__":
    unittest.main()
