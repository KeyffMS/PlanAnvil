from __future__ import annotations

from contextlib import nullcontext
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import live_codex_qualification_c10 as c10

C10_SOURCE = ROOT / "tools" / "live_codex_qualification_c10.py"
V7_SOURCE = ROOT / "tools" / "live_codex_qualification_harness_v7.py"


class LiveCodexC10Tests(unittest.TestCase):
    def test_v7_installs_deterministic_c10_runtime(self) -> None:
        source = V7_SOURCE.read_text(encoding="utf-8")
        self.assertIn("import live_codex_qualification_c10 as c10", source)
        self.assertIn("c10.install(v6, _live_runner_persisted_trust_runtime)", source)

    def test_c10_fixture_is_outer_harness_owned_and_product_validated(self) -> None:
        source = C10_SOURCE.read_text(encoding="utf-8")
        self.assertIn("v4._start_active_run(", source)
        self.assertIn("v4._create_checkpoint(planning=planning, run_root=run_root)", source)
        self.assertEqual(source.count("v4._checkpoint_validation(planning)"), 2)
        self.assertEqual(source.count("v4._checkpoint_validation(compact_planning)"), 2)
        self.assertIn('"fixture_prepared_by_outer_harness=true"', source)
        self.assertNotIn("planner_prompt", source)

    def test_postcompact_is_independent_of_session_start_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            hooks = {"hooks": {name: [{"hooks": [{"type": "command", "command": "fixture"}]}]
                               for name in ("SessionStart", "PreCompact", "PostCompact")}}
            c10.base.json_dump(repo / ".codex/hooks.json", hooks)
            self.assertTrue(c10._disable_session_start_for_postcompact(repo))
            remaining = c10.base.load_json(repo / ".codex/hooks.json")["hooks"]
            self.assertNotIn("SessionStart", remaining)
            self.assertEqual(remaining["PreCompact"], hooks["hooks"]["PreCompact"])
            self.assertEqual(remaining["PostCompact"], hooks["hooks"]["PostCompact"])

    def test_missing_compaction_handler_fails_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            c10.base.json_dump(repo / ".codex/hooks.json", {"hooks": {"SessionStart": []}})
            self.assertFalse(c10._disable_session_start_for_postcompact(repo))

    def test_compaction_trigger_is_qualification_only(self) -> None:
        source = C10_SOURCE.read_text(encoding="utf-8")
        self.assertIn('compat._set_feature(text, "token_budget", "false")', source)
        self.assertIn('"token_budget_disabled_in_isolated_fixture": True', source)
        self.assertIn("C10_SESSION_COMPACT_LIMIT = 1_000_000", source)
        self.assertIn("C10_COMPACT_LIMIT = 200", source)

    def test_opaque_recovery_value_is_not_persisted_in_evidence(self) -> None:
        secret_a, secret_b = "a" * 32, "b" * 32
        raw = {"error": "failure " + secret_a, "trials": [{"detail": "target=" + secret_b}]}
        redacted = c10._redact_proofs(raw, (secret_a, secret_b))
        self.assertNotIn(secret_a, json.dumps(redacted))
        self.assertNotIn(secret_b, json.dumps(redacted))
        self.assertIn(secret_a, raw["error"])
        self.assertFalse(c10._exact_echo({"observations": ["C10_RECOVERY_ECHO=" + secret_b]}, secret_a))
        self.assertTrue(c10._exact_echo({"observations": ["C10_RECOVERY_ECHO=" + secret_a]}, secret_a))

    def test_install_routes_only_c10(self) -> None:
        calls: list[dict[str, object]] = []

        def original(**kwargs: object) -> tuple[str, bool]:
            calls.append(dict(kwargs))
            return "ORIGINAL", False

        dummy = types.SimpleNamespace(_ORIGINAL_CAPABILITY_RUNTIME=original)
        trust = lambda: nullcontext(Path("."))
        with mock.patch.object(c10, "run_c10", return_value=("REPRODUCED", True)) as run_c10:
            c10.install(dummy, trust)
            self.assertEqual(
                dummy._ORIGINAL_CAPABILITY_RUNTIME(capability_id="C11", sentinel=1),
                ("ORIGINAL", False),
            )
            self.assertEqual(
                dummy._ORIGINAL_CAPABILITY_RUNTIME(capability_id="C10", sentinel=2),
                ("REPRODUCED", True),
            )
        self.assertEqual(calls, [{"capability_id": "C11", "sentinel": 1}])
        run_c10.assert_called_once_with(live_trust_runtime=trust, sentinel=2)

    def test_safety_boundary_is_not_weakened(self) -> None:
        source = C10_SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", source)
        self.assertNotIn("danger-full-access", source)
        self.assertNotIn("--privileged", source)
        self.assertNotIn("SYS_ADMIN", source)
        self.assertIn('sandbox="read-only"', source)
        self.assertIn("base.git_snapshot", source)


if __name__ == "__main__":
    unittest.main()
