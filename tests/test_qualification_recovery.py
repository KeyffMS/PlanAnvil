from __future__ import annotations

from contextlib import ExitStack
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import live_codex_qualification_recovery as recovery


class TargetedRecoveryTests(unittest.TestCase):
    def test_partial_scope_never_opens_release_gate(self) -> None:
        for failed in (None, "C09", "C10", "C13"):
            with self.subTest(failed=failed):
                results = {cid: "BLOCKED" if cid == failed else "REPRODUCED" for cid in recovery.SCOPE}
                summary = recovery.selected_summary(results)
                self.assertIs(summary["release_gate_passed"], False)
                self.assertEqual(summary["selected_gate_passed"], failed is None)
        self.assertFalse(recovery.selected_summary({})["selected_gate_passed"])

    def test_controller_uses_existing_runtime_and_continues_after_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root = Path(tmp) / "repo"
            (root / ".git/info").mkdir(parents=True)
            stack.enter_context(mock.patch.object(recovery.v7.prior, "_prepare_controller_root"))
            stack.enter_context(mock.patch.object(recovery.base, "codex_version", return_value="offline-test"))
            stack.enter_context(mock.patch.object(recovery.v7, "_install"))
            stack.enter_context(mock.patch("sys.stdout", new_callable=io.StringIO))
            observed = []

            def runtime(**kw):
                observed.append(kw["capability_id"])
                self.assertTrue(recovery.v7.v6.ALLOW_NON_EPHEMERAL_FALLBACK)
                if kw["capability_id"] == "C10":
                    raise RuntimeError("controlled offline fault")
                return "REPRODUCED", True

            stack.enter_context(mock.patch.object(recovery.v7.v6, "capability_runtime", side_effect=runtime))
            evidence = stack.enter_context(mock.patch.object(recovery.base, "write_evidence"))
            stack.enter_context(mock.patch.object(recovery.base, "local_commit"))
            index = stack.enter_context(mock.patch.object(recovery.base, "finalize_index"))
            artifact = stack.enter_context(mock.patch.object(recovery.base, "stage_artifact"))
            previous = recovery.v7.v6.ALLOW_NON_EPHEMERAL_FALLBACK
            rc = recovery.main([
                "--root", str(root), "--source-commit", "a" * 40,
                "--run-id", "offline", "--output", str(Path(tmp) / "artifact"),
                "--allow-c13-non-ephemeral-fallback",
            ])
            self.assertEqual(rc, 2)
            self.assertEqual(observed, ["C09", "C10", "C13"])
            self.assertEqual(evidence.call_args.kwargs["capability_id"], "C10")
            self.assertEqual(evidence.call_args.kwargs["result"], "BLOCKED")
            self.assertEqual(index.call_args.kwargs["results"]["C10"], "BLOCKED")
            self.assertFalse(artifact.call_args.args[2]["release_gate_passed"])
            self.assertFalse((root / ".qualification-runtime").exists())
            self.assertEqual(recovery.v7.v6.ALLOW_NON_EPHEMERAL_FALLBACK, previous)

    def test_live_trust_restores_config_on_exception_without_restoring_auth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            repo = Path(tmp) / "repo"
            home.mkdir()
            repo.mkdir()
            original = b'model = "offline"\n'
            config = home / "config.toml"
            config.write_bytes(original)
            auth = home / "auth.json"
            auth.write_text("original-auth", encoding="utf-8")
            common = recovery.base.common_codex_args
            with mock.patch.dict(os.environ, {"CODEX_HOME": str(home)}):
                with self.assertRaisesRegex(RuntimeError, "controlled"):
                    with recovery.v7._live_runner_persisted_trust_runtime():
                        recovery.base.common_codex_args(cwd=repo, sandbox="read-only",
                                                       schema=repo / "schema.json", output=repo / "out.json")
                        auth.write_text("refreshed-auth", encoding="utf-8")
                        raise RuntimeError("controlled")
                self.assertEqual(os.environ["CODEX_HOME"], str(home))
            self.assertEqual(config.read_bytes(), original)
            self.assertEqual(auth.read_text(encoding="utf-8"), "refreshed-auth")
            self.assertIs(recovery.base.common_codex_args, common)

    def test_recovery_workflow_keeps_existing_full_entrypoint(self) -> None:
        text = (ROOT / ".github/workflows/plananvil-codex-qualification.yml").read_text(encoding="utf-8")
        self.assertIn("          - recovery", text)
        full = text[text.index("  full:"):]
        self.assertIn("inputs.mode == 'recovery'", full)
        self.assertIn("python3 tools/live_codex_qualification_recovery.py", full)
        self.assertIn("python3 tools/live_codex_qualification_harness_v7.py", full)
        self.assertIn("qualification_args=(--allow-c13-non-ephemeral-fallback)", full)
        self.assertIn("refs/heads/main", full)


if __name__ == "__main__":
    unittest.main()
