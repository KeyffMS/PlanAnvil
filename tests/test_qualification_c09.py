from __future__ import annotations

from contextlib import ExitStack
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import qualification_c09 as c09
import qualification_process as observation
import live_codex_qualification_harness_v7 as v7
from test_qualification_execution_boundaries import execute_hook

v4 = v7.compat.v4
base = v4.base


def completed_payload():
    return {"capability_id": "C09", "trial": c09.TRIAL, "outcome": "PASS",
            "assertions": [], "observations": ["C09_FINISHED"], "blocker": None}


def valid_events():
    return {"event_types": {"turn.completed": 1}, "completed_command_items": 3,
            "event_tail": [{"event": "item.completed", "item": "command_execution",
                            "command": "c09_" + phase, "exit_code": 0, "c09_receipt_ok": True}
                           for phase in c09.PHASES]}


def valid_records():
    result = []
    for phase in c09.PHASES:
        result.append({"event": "PreToolUse", "c09_phase": phase, "returncode": 0})
        if phase != "finish":
            result += [{"event": "PreCompact", "trigger": "auto", "returncode": 0},
                       {"event": "PostCompact", "trigger": "auto", "returncode": 0},
                       {"event": "SessionStart", "source": "compact", "additional_context": True, "returncode": 0}]
    return result


class C09ProtocolTests(unittest.TestCase):
    def test_active_adapter_cannot_restore_the_old_200_token_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_c08 = v4.C08_COMPACT_LIMIT
            with v7.compat._codex0152_compaction(Path(tmp), "C09"):
                self.assertEqual(v4.C09_COMPACT_LIMIT, c09.COMPACT_LIMIT)
                self.assertEqual(v4.C09_COMPACT_LIMIT, 8192)
            self.assertEqual(v4.C08_COMPACT_LIMIT, old_c08)

    def test_file_fingerprint_detects_ignored_state_edits_but_not_git_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            path = repo / ".pursue/state.json"
            path.parent.mkdir()
            path.write_text('{"revision": 1}')
            before = c09.file_fingerprint(repo)
            (repo / ".git").mkdir()
            (repo / ".git/index").write_text("database")
            self.assertEqual(c09.file_fingerprint(repo), before)
            path.write_text('{"revision": 2}')
            self.assertNotEqual(c09.file_fingerprint(repo), before)

    def test_protocol_is_finite_and_explicit_about_completion(self):
        prompt = c09.prompt()
        for command in c09.COMMANDS.values():
            self.assertEqual(prompt.count(command), 1)
        self.assertIn("C09_FINISHED", prompt)
        self.assertIn("outcome PASS", prompt)
        self.assertIn("max_output_tokens=65536", prompt)

    def test_full_ordered_proof_passes(self):
        self.assertTrue(all(c09.protocol_checks(valid_events(), valid_records()).values()))

    def test_counts_alone_never_pass(self):
        checks = c09.protocol_checks({"completed_command_items": 20}, valid_records())
        self.assertFalse(checks["three_completed_reconciliations"])
        self.assertFalse(checks["turn_completed"])

    def test_reordered_repeated_missing_and_nonzero_tools_are_rejected(self):
        for mode in ("repeat", "reorder", "missing", "exit", "receipt", "truncated", "forbidden"):
            with self.subTest(mode=mode):
                events = valid_events()
                rows = events["event_tail"]
                if mode == "repeat": rows.append(rows[0])
                elif mode == "reorder": rows.reverse()
                elif mode == "missing": rows.pop()
                elif mode == "exit": rows[1]["exit_code"] = 2
                elif mode == "receipt": rows[1]["c09_receipt_ok"] = False
                elif mode == "truncated": events["event_tail_truncated"] = True
                elif mode == "forbidden": events["item_types"] = {"mcp_tool_call": 1}
                self.assertFalse(all(c09.protocol_checks(events, valid_records()).values()))

    def test_manual_compaction_missing_recovery_and_failed_hook_are_rejected(self):
        for mode in ("manual", "no_context", "failed", "wrong_order"):
            rows = valid_records()
            if mode == "manual": rows[1]["trigger"] = "manual"
            elif mode == "no_context": rows[3]["additional_context"] = False
            elif mode == "failed": rows[1]["returncode"] = 1
            else: rows[1], rows[2] = rows[2], rows[1]
            self.assertFalse(all(c09.protocol_checks(valid_events(), rows).values()))

    def test_cli_command_shapes_and_receipts_are_classified_without_content(self):
        receipt = {"c09_phase": "first", "checkpoint_ok": True,
                   "canonical_read": True, "git_reconciled": True}
        command = c09.COMMANDS["first"]
        self.assertEqual(observation.command_label(command), "c09_first")
        self.assertEqual(observation.command_label("/bin/bash -lc '" + command + "'"), "c09_first")
        self.assertEqual(observation.command_label(command + "; echo secret"), "other")
        collector = observation.StructuralEvents()
        collector.accept(json.dumps({"type": "item.completed", "item": {
            "type": "command_execution", "command": command, "exit_code": 0,
            "aggregated_output": "NEVER_PERSIST_THIS\n" + json.dumps(receipt) + "\nC09_NEXT=second\n",
        }}).encode())
        result = collector.summary()
        self.assertTrue(result["event_tail"][0]["c09_receipt_ok"])
        self.assertNotIn("NEVER_PERSIST_THIS", json.dumps(result))


class C09FixtureExecutionTests(unittest.TestCase):
    def test_real_install_checkpoint_three_readonly_commands_and_product_hooks(self):
        """Offline lifecycle driver; real product operations, NOT live Codex evidence."""
        with tempfile.TemporaryDirectory(prefix="c09 fixture ") as tmp:
            rt = Path(tmp)
            schemas = base.write_schemas(rt / "schemas")
            invoked = []

            def observed_driver(args, *, cwd, timeout):
                self.assertEqual(args[args.index("--sandbox") + 1], "read-only")
                self.assertIn("model_auto_compact_token_limit=8192", args)
                self.assertNotIn("--ignore-user-config", args)
                self.assertFalse(any("trust_level" in arg for arg in args))
                source = Path(base.git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")).parent
                configured = base.load_json(source / ".codex/hooks.json")["hooks"]
                collector = observation.StructuralEvents()

                def hook(name, tag, phase=None):
                    for group in configured.get(name, []):
                        if group.get("matcher") and not re.search(group["matcher"], tag):
                            continue
                        event = {"hook_event_name": name, "cwd": str(cwd), "source": tag, "trigger": tag}
                        if phase:
                            event.update(tool_name="Bash", tool_input={"command": c09.COMMANDS[phase]})
                        for handler in group["hooks"]:
                            result = execute_hook(handler["command"], cwd, event)
                            self.assertEqual(result.returncode, 0, result.stderr)
                            payload = json.loads(result.stdout) if result.stdout.strip() else {}
                            self.assertIsNot(payload.get("continue"), False)
                            if name == "SessionStart":
                                self.assertIn("C09_FINITE_RECOVERY", payload["hookSpecificOutput"]["additionalContext"])
                                self.assertNotIn("MAP_INSTRUCTIONS", payload["hookSpecificOutput"]["additionalContext"])

                hook("SessionStart", "startup")
                for phase in c09.PHASES:
                    hook("PreToolUse", "Bash", phase)
                    command = [sys.executable, "-B", c09.SCRIPT, phase]
                    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    invoked.append(phase)
                    self.assertNotIn(str(cwd), result.stdout)
                    if phase == "finish": self.assertLess(len(result.stdout), 2048)
                    else: self.assertGreater(len(result.stdout), c09.COMPACT_LIMIT * 8)
                    collector.accept(json.dumps({"type": "item.completed", "item": {
                        "type": "command_execution", "command": c09.COMMANDS[phase],
                        "exit_code": result.returncode, "aggregated_output": result.stdout,
                    }}).encode())
                    if phase != "finish":
                        hook("PreCompact", "auto")
                        hook("PostCompact", "auto")
                        hook("SessionStart", "compact")
                collector.accept(b'{"type":"turn.completed"}')
                events = collector.summary()
                events.update(process_cleanup_ok=True, process_returncode=0, timeout=False)
                base.json_dump(Path(args[args.index("-o") + 1]), completed_payload())
                return observation.ProcessResult(0, False, events)

            # An empty test home contains no credentials. The live path persists
            # trust and restores config exactly; only the model process is replaced.
            with mock.patch.dict(os.environ, {"CODEX_HOME": str(rt / "home")}), mock.patch.object(
                observation, "run_observed", side_effect=observed_driver
            ), mock.patch.object(v4, "_write_result", side_effect=lambda **kw: (kw["result"], True)) as writer:
                result, _ = v7.run_c09(root=ROOT, runtime_root=rt, schemas=schemas, version="codex-cli 0.153.4",
                                      os_name="offline", source_commit="b" * 40, date="2026-09-06")
            self.assertEqual(result, "REPRODUCED", writer.call_args.kwargs)
            self.assertEqual(invoked, list(c09.PHASES))
            self.assertTrue(all(writer.call_args.kwargs["trials"][0]["protocol_checks"].values()))
            self.assertFalse((rt / "home/config.toml").exists())
            # Locate the active planning root from the copied, unchanged helper.
            helpers = list((rt / "C09").rglob("c09_probe.py"))
            for helper in helpers:
                candidate = helper.parents[1]
                states = list((candidate / ".pursue/runs").glob("*/state.json"))
                if states:
                    state = json.loads(states[0].read_text())
                    state["next_action"]["type"] = "MAP_INSTRUCTIONS"
                    states[0].write_text(json.dumps(state))
                    proc = subprocess.run([sys.executable, "-B", str(helper), "finish"], cwd=candidate,
                                          capture_output=True, text=True, timeout=30)
                    self.assertNotEqual(proc.returncode, 0)
                    break
            else:
                self.fail("Planning fixture was not available for negative checkpoint test")


if __name__ == "__main__":
    unittest.main()
