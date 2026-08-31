from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "live_codex_qualification.py"
SPEC = importlib.util.spec_from_file_location("live_codex_qualification", MODULE_PATH)
assert SPEC and SPEC.loader
live = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(live)


class LiveCodexQualificationTests(unittest.TestCase):
    def test_sanitize_redacts_tokens_sessions_and_private_paths(self) -> None:
        raw = (
            "token=ghp_abcdefghijklmnop path=/home/alice/project/file "
            "session=01a05825-18c0-78b2-a231-0ed1bcaf5be1"
        )
        value = live.sanitize_text(raw)
        self.assertNotIn("ghp_abcdefghijklmnop", value)
        self.assertNotIn("/home/alice", value)
        self.assertNotIn("01a05825-18c0-78b2-a231-0ed1bcaf5be1", value)
        self.assertIn("<REDACTED_TOKEN>", value)
        self.assertIn("<PATH>", value)
        self.assertIn("<SESSION_ID>", value)

    def test_event_summary_retains_structure_not_content(self) -> None:
        stream = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "secret"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "command_execution",
                            "command": "cat /home/alice/.codex/auth.json",
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "file_change", "path": "/home/alice/file"},
                    }
                ),
            ]
        )
        summary = live.event_summary(stream)
        self.assertEqual(summary["completed_command_items"], 1)
        self.assertEqual(summary["completed_file_change_items"], 1)
        self.assertNotIn("secret", json.dumps(summary))
        self.assertNotIn("/home/alice", json.dumps(summary))

    def test_common_codex_args_are_ephemeral_sandboxed_and_noninteractive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            schema = root / "schema.json"
            output = root / "output.json"
            schema.write_text("{}\n", encoding="utf-8")
            args = live.common_codex_args(
                cwd=root,
                sandbox="workspace-write",
                schema=schema,
                output=output,
                add_dir=root / "worktrees",
                trust_project=True,
                hook_trust=True,
            )
        joined = " ".join(args)
        self.assertIn("exec", args)
        self.assertIn("--ephemeral", args)
        self.assertIn("--ignore-user-config", args)
        self.assertIn("--sandbox", args)
        self.assertIn("workspace-write", args)
        self.assertIn('approval_policy="never"', args)
        self.assertIn("sandbox_workspace_write.network_access=false", args)
        self.assertIn("--dangerously-bypass-hook-trust", args)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", args)
        self.assertNotIn("danger-full-access", joined)

    def test_validate_plan_rejects_duplicate_trials(self) -> None:
        plan = {
            "capability_id": "C01",
            "setup_summary": [],
            "trials": [
                {
                    "name": "same",
                    "prompt": "a",
                    "sandbox": "read-only",
                    "reset_before": True,
                },
                {
                    "name": "same",
                    "prompt": "b",
                    "sandbox": "read-only",
                    "reset_before": True,
                },
            ],
        }
        self.assertIn("duplicate", live.validate_plan("C01", plan) or "")


if __name__ == "__main__":
    unittest.main()
