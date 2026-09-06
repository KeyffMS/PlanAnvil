from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import qualification_process as process
import qualification_c10_observation as c10obs
import live_codex_qualification_c10 as c10
import live_codex_qualification_harness_v4 as v4


class StructuralObservationTests(unittest.TestCase):
    def test_content_is_not_retained_and_commands_are_exactly_classified(self):
        secret = "do-not-store-opaque-private-content"
        collector = process.StructuralEvents()
        events = [
            {"type": "thread.started", "thread_id": secret},
            {"type": "item.completed", "item": {"type": "command_execution", "command":
                "/bin/bash -lc 'cat qualification-payload/segment-01.txt'", "aggregated_output": secret,
                "exit_code": 0, "status": "completed"}},
            {"type": "item.completed", "item": {"type": "error", "message": "hook failed " + secret}},
            {"type": secret, "item": {"type": secret, "status": secret}},
            {"type": "turn.failed", "error": {"message": "401 Unauthorized " + secret}},
        ]
        for event in events:
            collector.accept(json.dumps(event).encode())
        collector.accept(secret.encode(), stderr=True)
        result = collector.summary()
        self.assertEqual(result["completed_command_items"], 1)
        self.assertEqual(result["command_counts"], {"segment_01": 1})
        self.assertEqual(result["error_categories"]["hook_error"], 1)
        self.assertEqual(result["error_categories"]["unauthorized"], 1)
        self.assertNotIn(secret, json.dumps(result))
        self.assertEqual(process.command_label("cat qualification-payload/segment-01.txt; rm x"), "other")

    def test_event_history_is_bounded_and_totals_remain_complete(self):
        collector = process.StructuralEvents()
        for _ in range(process.MAX_EVENTS + 50):
            collector.accept(b'{"type":"turn.started"}')
        result = collector.summary()
        self.assertEqual(len(result["event_tail"]), process.MAX_EVENTS)
        self.assertTrue(result["event_tail_truncated"])
        self.assertEqual(result["event_types"]["turn.started"], process.MAX_EVENTS + 50)

    def test_malformed_oversized_and_non_object_json_are_bounded(self):
        collector = process.StructuralEvents()
        stream = io.BytesIO(b'x' * (process.MAX_LINE_BYTES + 30) + b'\ninvalid\n[]\n{"type":"turn.completed"}\n')
        collector.read(stream)
        result = collector.summary()
        self.assertEqual(result["oversized_lines"], 1)
        self.assertEqual(result["invalid_json_lines"], 2)
        self.assertEqual(result["event_types"], {"turn.completed": 1})

    def test_successful_real_process_keeps_terminal_event_without_content(self):
        secret = "ghp_0123456789abcdefghijklmnop"
        program = 'import json,sys; print(json.dumps({"type":"turn.completed","secret":' + repr(secret) + '})); print(' + repr(secret) + ',file=sys.stderr)'
        with tempfile.TemporaryDirectory() as tmp:
            result = process.run_observed([sys.executable, "-c", program], cwd=Path(tmp), timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.timed_out)
        self.assertTrue(result.events["process_cleanup_ok"])
        self.assertEqual(result.events["event_types"]["turn.completed"], 1)
        self.assertNotIn(secret, json.dumps(result.events))

    def test_real_timeout_retains_progress_and_kills_owned_descendant(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / "escaped-child.txt"
            child = f'import time,pathlib; time.sleep(5); pathlib.Path({str(marker)!r}).write_text("escaped")'
            parent = ('import subprocess,sys,time,json; '
                      'print(json.dumps({"type":"item.completed","item":{"type":"command_execution",'
                      '"command":"cat qualification-payload/segment-02.txt","exit_code":0}}),flush=True); '
                      f'subprocess.Popen([sys.executable,"-c",{child!r}]); time.sleep(30)')
            result = process.run_observed([sys.executable, "-c", parent], cwd=root, timeout=3)
            self.assertTrue(result.timed_out)
            self.assertTrue(result.events["owned_process_tree_terminated"])
            self.assertTrue(result.events["process_cleanup_ok"])
            self.assertEqual(result.events["command_counts"], {"segment_02": 1})
            time.sleep(5.2)
            self.assertFalse(marker.exists(), "A descendant survived timeout and changed state")


class RecoveryValueFlowTests(unittest.TestCase):
    def test_format_diagnostics_do_not_weaken_exact_echo(self):
        proof = "1234" * 8
        for value, classification, passed in [
            ("C10_RECOVERY_ECHO=" + proof, "exact", True),
            ("`C10_RECOVERY_ECHO=" + proof + "`", "expected_value_wrong_format", False),
            ("C10_RECOVERY_ECHO=" + "5678" * 8, "different_value", False),
            ("CONTEXT_MISSING", "no_echo", False),
        ]:
            with self.subTest(classification=classification):
                payload = {"observations": [value]}
                result = c10obs.echo_diagnostics(payload, proof)
                self.assertEqual(result["classification"], classification)
                self.assertEqual(c10._exact_echo(payload, proof), passed)
                self.assertNotIn(proof, json.dumps(result))
        result = c10obs.echo_diagnostics({"observations": [], "assertions": [{"evidence": proof}]}, proof)
        self.assertTrue(result["expected_value_elsewhere"])
        self.assertFalse(result["exact_observation"])

    def run_proxy(self, root, proof, emitted, *, exitcode=0, event_name="SessionStart", stdout=None):
        hooks = root / ".codex/hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        # No model, no Codex. Test the generated subprocess contract itself.
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (hooks / "proxy.py").write_text(c10obs.proxy_source(proof), encoding="utf-8")
        output = stdout if stdout is not None else json.dumps({"hookSpecificOutput": {
            "hookEventName": event_name, "additionalContext": f"target evidence/c10-recovery-{emitted}.json"}})
        (hooks / "product.py").write_text(f'import sys; print({output!r}); raise SystemExit({exitcode})\n', encoding="utf-8")
        completed = subprocess.run([sys.executable, str(hooks / "proxy.py"), "SessionStart", "product.py"],
            cwd=root, input=json.dumps({"hook_event_name": "SessionStart", "source": "compact", "cwd": str(root)}), text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=10)
        self.assertEqual(completed.returncode, exitcode)
        self.assertEqual(completed.stdout, output + "\n")
        return completed

    def test_proxy_compares_actual_product_value_without_retaining_it(self):
        proof = "abcd" * 8
        for emitted, match in [(proof, True), ("1234" * 8, False)]:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.run_proxy(root, proof, emitted)
                text = (root / ".pursue/qualification-hook-events.jsonl").read_text()
                record = json.loads(text)
                self.assertEqual(record["recovery_target_matches_expected"], match)
                self.assertTrue(record["output_event_matches_input"])
                self.assertNotIn(proof, text)
                self.assertNotIn(emitted, text)
                self.assertNotIn(proof, (root / ".codex/hooks/proxy.py").read_text())

    def test_proxy_preserves_nonzero_exit_invalid_json_and_wrong_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.run_proxy(root, "a" * 32, "b" * 32, exitcode=7, stdout="not-json")
            record = json.loads((root / ".pursue/qualification-hook-events.jsonl").read_text())
            self.assertEqual(record["returncode"], 7)
            self.assertFalse(record["product_stdout_is_json"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.run_proxy(root, "a" * 32, "a" * 32, event_name="PostCompact")
            record = json.loads((root / ".pursue/qualification-hook-events.jsonl").read_text())
            self.assertFalse(record["output_event_matches_input"])

    def test_recorder_failure_does_not_change_product_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".pursue").write_text("blocks logging")
            self.run_proxy(root, "a" * 32, "a" * 32)

    def test_probe_observes_before_sanitizing_but_does_not_return_raw_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "trial-01.json"
            proof = "a" * 32
            payload = {"observations": ["C10_RECOVERY_ECHO=" + proof], "blocker": "/home/private/secret"}
            def fake_run(args, **kw):
                v4.base.json_dump(output, payload)
                return process.ProcessResult(0, False, {"process_cleanup_ok": True})
            with mock.patch.object(process, "run_observed", side_effect=fake_run):
                parsed, events, error = v4._run_codex_probe(cwd=root, prompt="test", schemas={"trial": root / "schema"},
                    results_dir=root, position=1, sandbox="read-only", observe_process=True,
                    inspect_payload=lambda value: c10obs.echo_diagnostics(value, proof))
            self.assertIsNone(error)
            self.assertTrue(events["raw_payload_checks"]["exact_observation"])
            self.assertNotIn(proof, json.dumps(events))
            self.assertEqual(parsed["blocker"], "<PATH>")

    def test_probe_timeout_keeps_events_and_never_accepts_stale_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            v4.base.json_dump(root / "trial-01.json", {"outcome": "PASS"})
            partial = {"process_cleanup_ok": True, "timeout": True, "completed_command_items": 2}
            with mock.patch.object(process, "run_observed", return_value=process.ProcessResult(-9, True, partial)):
                payload, events, error = v4._run_codex_probe(cwd=root, prompt="test", schemas={"trial": root / "schema"},
                    results_dir=root, position=1, sandbox="read-only", observe_process=True)
            self.assertEqual(payload, {})
            self.assertEqual(events["completed_command_items"], 2)
            self.assertIn("timed out", error)
            self.assertFalse((root / "trial-01.json").exists())


if __name__ == "__main__":
    unittest.main()
