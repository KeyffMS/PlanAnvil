from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from _helpers import init_repo, run
from common import PlanAnvilError, atomic_write_json, load_json, sha256_file
from preflight import preflight
from transition_state import transition_state

ROOT = Path(__file__).resolve().parents[4]
HOOKS = ROOT / ".codex/hooks"


class HookAndEdgeStateTests(unittest.TestCase):
    def _hook(self, script: str, repo: Path, event: dict) -> dict:
        result = subprocess.run(
            ["python3", str(HOOKS / script)],
            cwd=repo,
            input=json.dumps(event),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def _active_repo(self, root: Path, *, mode: str = "PLAN_GENERATION", checkpoint=None) -> Path:
        repo = init_repo(root / "repo")
        state = {
            "schema_version": "1.1.0",
            "revision": 1,
            "updated_at": "2026-07-12T12:00:00Z",
            "mode": mode,
            "status": "PROFILE_READY" if mode == "PLAN_GENERATION" else "EXECUTION_IN_PROGRESS",
            "current_stage": None,
            "current_phase": "DISCOVER_INSTRUCTIONS",
            "next_action": {"type": "MAP_INSTRUCTIONS", "target": "evidence/instruction-map.json"},
            "last_checkpoint": checkpoint,
            "open_blockers": [],
            "artifact_hashes": {},
        }
        path = repo / ".pursue/runs/run/state.json"
        path.parent.mkdir(parents=True)
        atomic_write_json(path, state)
        return repo

    def _write_valid_checkpoint(self, repo: Path) -> Path:
        run_root = repo / ".pursue/runs/run"
        state_path = run_root / "state.json"
        state = load_json(state_path)
        checkpoint_path = run_root / "checkpoints/CHECKPOINT-01-VERIFIED.json"
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        branch = run("git", "branch", "--show-current", cwd=repo).stdout.strip()
        head = run("git", "rev-parse", "HEAD", cwd=repo).stdout.strip()
        checkpoint = {
            "schema_version": "1.1.0",
            "id": "CHECKPOINT-01-VERIFIED",
            "created_at": "2026-07-12T12:05:00Z",
            "mode": state["mode"],
            "stage": None,
            "phase": state["current_phase"],
            "result": "PASS",
            "git": {
                "branch": branch,
                "head": head,
                "worktree_role": "PLANNING",
                "status": "DIRTY",
            },
            "tests": {"summary": "No pending test failure.", "evidence": []},
            "risks": {"open": [], "closed": []},
            "agent_tree": {"status": "COMPLIANT", "evidence": []},
            "write_scope": {"status": "COMPLIANT", "evidence": []},
            "next_action": state["next_action"],
            "recovery": ["Read canonical state and reconcile the recorded Git worktree."],
            "artifact_hashes": {},
        }
        atomic_write_json(checkpoint_path, checkpoint)
        state["last_checkpoint"] = "checkpoints/CHECKPOINT-01-VERIFIED.json"
        state["artifact_hashes"][state["last_checkpoint"]] = sha256_file(checkpoint_path)
        atomic_write_json(state_path, state)
        return checkpoint_path

    def test_hook_denies_destructive_git_and_product_patch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = self._active_repo(Path(directory))
            common = {"cwd": str(repo), "hook_event_name": "PreToolUse", "tool_name": "Bash"}
            denied = self._hook(
                "plan-anvil-guard.py",
                repo,
                {**common, "tool_input": {"command": "git reset --hard HEAD"}},
            )
            self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")
            allowed = self._hook(
                "plan-anvil-guard.py",
                repo,
                {**common, "tool_input": {"command": "git status --short"}},
            )
            self.assertEqual(allowed, {})

            patch = "*** Begin Patch\n*** Update File: src/app.py\n@@\n-old\n+new\n*** End Patch\n"
            denied_patch = self._hook(
                "plan-anvil-guard.py",
                repo,
                {
                    "cwd": str(repo),
                    "hook_event_name": "PreToolUse",
                    "tool_name": "apply_patch",
                    "tool_input": {"command": patch},
                },
            )
            self.assertEqual(denied_patch["hookSpecificOutput"]["permissionDecision"], "deny")
            denied_write = self._hook(
                "plan-anvil-guard.py",
                repo,
                {
                    "cwd": str(repo),
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Write",
                    "tool_input": {"file_path": "src/app.py", "content": "changed"},
                },
            )
            self.assertEqual(denied_write["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_hook_allows_control_patch_and_compaction_requires_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = self._active_repo(Path(directory))
            patch = "*** Begin Patch\n*** Update File: .pursue/runs/run/PLAN.md\n@@\n-old\n+new\n*** End Patch\n"
            allowed = self._hook(
                "plan-anvil-guard.py",
                repo,
                {
                    "cwd": str(repo),
                    "hook_event_name": "PreToolUse",
                    "tool_name": "apply_patch",
                    "tool_input": {"command": patch},
                },
            )
            self.assertEqual(allowed, {})
            allowed_write = self._hook(
                "plan-anvil-guard.py",
                repo,
                {
                    "cwd": str(repo),
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Write",
                    "tool_input": {"file_path": ".pursue/runs/run/PLAN.md", "content": "plan"},
                },
            )
            self.assertEqual(allowed_write, {})

        with tempfile.TemporaryDirectory() as directory:
            repo = self._active_repo(Path(directory), mode="PLAN_EXECUTION")
            blocked = self._hook(
                "plan-anvil-compaction.py",
                repo,
                {"cwd": str(repo), "hook_event_name": "PreCompact", "trigger": "auto"},
            )
            self.assertFalse(blocked["continue"])
            self.assertIn("checkpoint", blocked["stopReason"].lower())

    def test_compaction_rejects_missing_checkpoint_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = self._active_repo(
                Path(directory),
                mode="PLAN_EXECUTION",
                checkpoint="checkpoints/CHECKPOINT-01-VERIFIED.json",
            )
            blocked = self._hook(
                "plan-anvil-compaction.py",
                repo,
                {"cwd": str(repo), "hook_event_name": "PreCompact", "trigger": "manual"},
            )
            self.assertFalse(blocked["continue"])
            self.assertIn("missing", blocked["stopReason"].lower())

    def test_compaction_accepts_schema_and_git_valid_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = self._active_repo(Path(directory), mode="PLAN_EXECUTION")
            checkpoint_path = self._write_valid_checkpoint(repo)
            allowed = self._hook(
                "plan-anvil-compaction.py",
                repo,
                {"cwd": str(repo), "hook_event_name": "PreCompact", "trigger": "manual"},
            )
            self.assertEqual(allowed, {})

            recovery = self._hook(
                "plan-anvil-recovery.py",
                repo,
                {"cwd": str(repo), "hook_event_name": "SessionStart", "source": "resume"},
            )
            message = recovery["hookSpecificOutput"]["additionalContext"]
            self.assertIn("Validated checkpoint", message)
            self.assertIn(str(checkpoint_path), message)

    def test_detached_head_with_multiple_containing_branches_is_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = init_repo(Path(directory) / "repo")
            run("git", "branch", "other", cwd=repo)
            sha = run("git", "rev-parse", "HEAD", cwd=repo).stdout.strip()
            run("git", "checkout", "--detach", sha, cwd=repo)
            result = preflight(repo)
            self.assertFalse(result["ok"])
            self.assertEqual(result["result"], "GIT_BASE_AMBIGUOUS")
            self.assertEqual(result["plan_status"], "BLOCKED_BY_GIT_STATE")

    def test_state_revision_and_order_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            atomic_write_json(
                state_path,
                {
                    "schema_version": "1.1.0",
                    "revision": 0,
                    "updated_at": "2026-07-12T12:00:00Z",
                    "mode": "PLAN_GENERATION",
                    "status": "PROFILE_READY",
                    "current_stage": None,
                    "current_phase": "DISCOVER_INSTRUCTIONS",
                    "next_action": {"type": "MAP_INSTRUCTIONS", "target": "evidence/instruction-map.json"},
                    "last_checkpoint": None,
                    "open_blockers": [],
                    "artifact_hashes": {},
                },
            )
            with self.assertRaises(PlanAnvilError) as stale:
                transition_state(
                    state_path,
                    expected_revision=1,
                    new_status="INSTRUCTION_MAP_READY",
                    phase="ANALYZE_GOAL",
                    next_action_type="ANALYZE_GOAL",
                    next_action_target="PLAN.md",
                )
            self.assertEqual(stale.exception.code, "STALE_STATE_REVISION")
            with self.assertRaises(PlanAnvilError) as skipped:
                transition_state(
                    state_path,
                    expected_revision=0,
                    new_status="ARTIFACTS_GENERATED",
                    phase="DETERMINISTIC_VALIDATION",
                    next_action_type="RUN_VALIDATOR",
                    next_action_target="reports/validation/summary.json",
                )
            self.assertEqual(skipped.exception.code, "INVALID_STATE_TRANSITION")


if __name__ == "__main__":
    unittest.main()
