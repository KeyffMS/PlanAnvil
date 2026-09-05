from __future__ import annotations

from contextlib import ExitStack, nullcontext
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import live_codex_qualification_c10 as c10
import live_codex_qualification_harness_v4 as v4
import live_codex_qualification_harness_v7 as v7

base = v4.base


def execute_hook(command: str, cwd: Path, event: dict) -> subprocess.CompletedProcess[str]:
    # Execute the actual generated POSIX command on the live runner's platform.
    # Windows exercises the same generated Python program and argument contract.
    if os.name == "nt":
        argv = shlex.split(command.replace("$(git rev-parse --show-toplevel)", str(cwd)))
        argv[0] = sys.executable
    else:
        argv = ["/bin/sh", "-c", command]
    return subprocess.run(
        argv, cwd=cwd, input=json.dumps(event), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False,
    )


class SubagentProcessContractTests(unittest.TestCase):
    def test_active_c13_configuration_executes_its_generated_proxy(self) -> None:
        with tempfile.TemporaryDirectory(prefix="plananvil c13 ") as tmp:
            root = Path(tmp)
            repo = root / "project with spaces"
            proof = "c" * 32
            captured = {}

            def probe(**_kwargs):
                base.ensure_git_repo(repo)
                v7._seed_declared_project_fixture(repo, proof)
                base.commit_fixture_baseline(repo)
                command = base.load_json(repo / ".codex/hooks.json")["hooks"]["SubagentStart"][0]["hooks"][0]["command"]
                log = v7.prior._hook_log(repo)
                with v7.compat.regression._hook_env(log):
                    before = base.git_snapshot(repo)
                    completed = execute_hook(command, repo, {
                        "hook_event_name": "SubagentStart", "cwd": str(repo),
                        "agent_type": "fixture_agent", "session_id": "offline-test",
                    })
                    after = base.git_snapshot(repo)
                captured.update(completed=completed, before=before, after=after,
                                records=v7.prior._read_hook_records(repo))
                return "OFFLINE_ONLY", False

            # Same compatibility context and project fixture used by v7 live C13.
            v7.compat.run_c13(probe, runtime_root=root)
            completed = captured["completed"]
            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = json.loads(completed.stdout)
            self.assertIs(output["continue"], False)
            self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "SubagentStart")
            self.assertEqual(output["hookSpecificOutput"]["additionalContext"], "C13_CONTEXT_TOKEN=" + proof)
            self.assertEqual(len(captured["records"]), 1)
            self.assertEqual(captured["records"][0]["event"], "SubagentStart")
            self.assertEqual(captured["records"][0]["returncode"], 0)
            self.assertEqual(captured["before"], captured["after"])


class CompactionCompletionTests(unittest.TestCase):
    def evaluate(self, payload, events, error, records=None):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root = Path(tmp)
            if records is None:
                records = [
                    {"event": "PreCompact"}, {"event": "PostCompact"},
                    {"event": "PreCompact"}, {"event": "PostCompact"},
                    {"event": "PreToolUse"},
                ]
            stack.enter_context(mock.patch.object(v4, "_runtime_paths", return_value=(root,) * 7))
            stack.enter_context(mock.patch.object(base, "ensure_git_repo"))
            stack.enter_context(mock.patch.object(base, "git", return_value="a" * 40))
            stack.enter_context(mock.patch.object(base, "git_snapshot", return_value={"head": "a" * 40}))
            stack.enter_context(mock.patch.object(v4, "_start_active_run", return_value=(root, ".pursue/runs/test")))
            stack.enter_context(mock.patch.object(v4, "_checkpoint_validation", return_value={"ok": True}))
            stack.enter_context(mock.patch.object(v4, "_clear_hook_log"))
            stack.enter_context(mock.patch.object(v4, "_read_hook_records", return_value=records))
            stack.enter_context(mock.patch.object(v4, "_run_codex_probe", return_value=(payload, events, error)))
            writer = stack.enter_context(mock.patch.object(v4, "_write_result", side_effect=lambda **kw: (kw["result"], True)))
            v4._c09_runtime(root=root, runtime_root=root, schemas={}, version="offline",
                            os_name="test", source_commit="b" * 40, date="2026-09-05")
            return writer.call_args.kwargs

    def test_timeout_cannot_pass_even_after_two_compactions(self) -> None:
        result = self.evaluate({}, {"timeout": True}, "Codex invocation timed out")
        self.assertEqual(result["result"], "BLOCKED")
        self.assertFalse(result["expected_met"])
        self.assertNotEqual(result["trials"][0]["outcome"], "PASS")

    def test_missing_completion_payload_cannot_pass(self) -> None:
        result = self.evaluate({}, {}, None)
        self.assertEqual(result["result"], "BLOCKED")

    def test_completed_positive_trial_still_passes(self) -> None:
        result = self.evaluate({"capability_id": "C09", "outcome": "PASS"}, {}, None)
        self.assertEqual(result["result"], "REPRODUCED")
        self.assertTrue(result["expected_met"])

    def test_second_compaction_still_requires_subsequent_tool_use(self) -> None:
        result = self.evaluate({"capability_id": "C09", "outcome": "PASS"}, {}, None,
                               [{"event": "PreCompact"}, {"event": "PostCompact"}] * 2)
        self.assertNotEqual(result["result"], "REPRODUCED")

    def test_observed_stop_with_valid_checkpoint_still_fails(self) -> None:
        result = self.evaluate({"capability_id": "C09", "outcome": "PASS"}, {}, None,
                               [{"event": "PreCompact", "continue": False},
                                {"event": "PostCompact"}] * 2 + [{"event": "PreToolUse"}])
        self.assertEqual(result["result"], "FAILED")


class RecoveryFixtureExecutionTests(unittest.TestCase):
    def test_both_recovery_trials_use_independent_correctly_scoped_fixtures(self) -> None:
        """Offline lifecycle driver, NOT evidence of a live Codex capability.

        Only the Codex process is replaced. Git, the release installer, start,
        checkpoint creator/validator, generated commands and product hooks run.
        The driver deliberately reads declarations from the root checkout, as
        rust-v0.153.4 config/src/loader/mod.rs does for linked worktrees.
        """
        with tempfile.TemporaryDirectory(prefix="plananvil c10 ") as tmp:
            runtime = Path(tmp)
            schemas = base.write_schemas(runtime / "schemas")
            actual_run = base.run
            roots = []
            configured_events = []
            proofs = []

            def driver(args, *, cwd, **kwargs):
                if args[0] != "codex":
                    return actual_run(args, cwd=cwd, **kwargs)
                self.assertEqual(len(roots) < 2, True, "Unexpected extra Codex invocation")
                self.assertEqual(args[args.index("--sandbox") + 1], "read-only")
                common_dir = Path(actual_run(
                    ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                    cwd=cwd, timeout=30,
                ).stdout.strip())
                source = common_dir.parent
                roots.append(source)
                hooks = base.load_json(source / ".codex/hooks.json")["hooks"]
                configured_events.append(set(hooks))
                postcompact = len(roots) == 2
                lifecycle = [("SessionStart", "startup")]
                if postcompact:
                    lifecycle += [("PreCompact", "auto"), ("PostCompact", "auto"),
                                  ("SessionStart", "compact")]
                contexts = []
                for event_name, trigger in lifecycle:
                    for group in hooks.get(event_name, []):
                        if group.get("matcher") and not re.search(group["matcher"], trigger):
                            continue
                        for handler in group["hooks"]:
                            event = {"hook_event_name": event_name, "cwd": str(cwd),
                                     "source": trigger, "trigger": trigger, "session_id": "offline-test"}
                            completed = execute_hook(handler["command"], cwd, event)
                            self.assertEqual(completed.returncode, 0, completed.stderr)
                            parsed = json.loads(completed.stdout) if completed.stdout.strip() else {}
                            self.assertIsNot(parsed.get("continue"), False, parsed)
                            context = parsed.get("hookSpecificOutput", {}).get("additionalContext")
                            if context:
                                contexts.append(context)
                matches = re.findall(r"evidence/c10-recovery-([0-9a-f]{32})\.json", "\n".join(contexts))
                self.assertTrue(matches, "The real product hook did not return the fixture recovery pointer")
                proof = matches[-1]
                proofs.append(proof)
                payload = {
                    "capability_id": "C10",
                    "trial": "postcompact_recovery_context" if postcompact else "session_start_recovery_context",
                    "outcome": "PASS", "assertions": [], "blocker": None,
                    "observations": ["C10_RECOVERY_ECHO=" + proof],
                }
                base.json_dump(Path(args[args.index("-o") + 1]), payload)
                events = [{"type": "turn.started"}]
                if postcompact:
                    events.append({"type": "item.completed", "item": {
                        "id": "offline-command", "type": "command_execution",
                        "command": "cat qualification-payload/segment-01.txt",
                        "status": "completed", "exit_code": 0, "aggregated_output": "fixture payload",
                    }})
                events.append({"type": "turn.completed"})
                return subprocess.CompletedProcess(args, 0, "\n".join(map(json.dumps, events)), "")

            with mock.patch.object(base, "run", side_effect=driver), mock.patch.object(
                v4, "_write_result", side_effect=lambda **kw: (kw["result"], True)
            ) as writer:
                result, _required = c10.run_c10(
                    root=ROOT, runtime_root=runtime, schemas=schemas, version="codex-cli 0.153.4",
                    os_name="offline-test", source_commit="b" * 40, date="2026-09-05",
                    live_trust_runtime=lambda: nullcontext(runtime),
                )
            evidence = writer.call_args.kwargs
            self.assertEqual(result, "REPRODUCED", evidence)
            self.assertEqual(len(roots), 2)
            self.assertNotEqual(roots[0], roots[1], "A second invocation must not reuse the first source checkout")
            self.assertIn("SessionStart", configured_events[0])
            self.assertNotIn("SessionStart", configured_events[1])
            self.assertIn("PreCompact", configured_events[1])
            self.assertIn("PostCompact", configured_events[1])
            self.assertNotEqual(proofs[0], proofs[1], "Recovery probes must have independent proof values")
            for proof in proofs:
                self.assertNotIn(proof, json.dumps(evidence, default=str), "Opaque proof leaked into persisted evidence")


if __name__ == "__main__":
    unittest.main()
