from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from _helpers import cleanup_worktree, init_repo, run

from common import PlanAnvilError
from create_planning_worktree import create_planning_worktree
from preflight import preflight
from test_git_capabilities import probe_git_capabilities


class PreflightAndGitTests(unittest.TestCase):
    def test_clean_and_dirty_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp) / "repo")
            clean = preflight(repo)
            self.assertTrue(clean["ok"], clean)
            (repo / "untracked.txt").write_text("x", encoding="utf-8")
            dirty = preflight(repo)
            self.assertEqual(dirty["result"], "GIT_DIRTY")
            self.assertEqual(dirty["plan_status"], "BLOCKED_BY_GIT_STATE")

    def test_complete_probe_preserves_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = init_repo(root / "repo")
            before = preflight(repo)["source_snapshot"]
            result = probe_git_capabilities(repo, "probe-001", root / "external")
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["result"], "GIT_READY")
            self.assertEqual(preflight(repo)["source_snapshot"], before)
            self.assertFalse((root / "external/probe-001").exists())

    def test_planning_worktree_is_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = init_repo(root / "repo")
            capability = probe_git_capabilities(repo, "probe-002", root / "external")
            plan_id = "PG-20260712-143000-A1B2"
            info = create_planning_worktree(
                repo,
                plan_id=plan_id,
                slug="example",
                capability_report=capability,
                destination=root / "planning",
            )
            try:
                self.assertEqual(run("git", "branch", "--show-current", cwd=repo).stdout.strip(), "main")
                self.assertEqual(
                    run("git", "branch", "--show-current", cwd=Path(info["planning_worktree"])).stdout.strip(),
                    info["planning_branch"],
                )
                self.assertEqual(run("git", "status", "--porcelain", cwd=repo).stdout, "")
            finally:
                cleanup_worktree(repo, Path(info["planning_worktree"]), info["planning_branch"])

    def test_probe_and_planning_destinations_must_be_external(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = init_repo(root / "repo")
            with self.assertRaises(PlanAnvilError) as probe_error:
                probe_git_capabilities(repo, "probe-inside", repo / ".probe")
            self.assertEqual(probe_error.exception.code, "PROBE_TEMP_INSIDE_WORKTREE")

            capability = probe_git_capabilities(repo, "probe-external", root / "external")
            with self.assertRaises(PlanAnvilError) as worktree_error:
                create_planning_worktree(
                    repo,
                    plan_id="PG-20260712-143000-A1B2",
                    slug="inside",
                    capability_report=capability,
                    destination=repo / "planning",
                )
            self.assertEqual(worktree_error.exception.code, "PLANNING_WORKTREE_INSIDE_WORKTREE")

    def test_probe_failure_cleans_resources_and_reports_hook_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = init_repo(root / "repo")
            hooks = Path(run("git", "rev-parse", "--git-path", "hooks", cwd=repo).stdout.strip())
            if not hooks.is_absolute():
                hooks = repo / hooks
            hooks.mkdir(parents=True, exist_ok=True)
            hook = hooks / "pre-commit"
            hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8", newline="\n")
            hook.chmod(0o755)
            result = probe_git_capabilities(repo, "probe-hook-block", root / "external")
            self.assertFalse(result["ok"], result)
            self.assertEqual(result["result"], "GIT_HOOK_BLOCKED")
            self.assertEqual(result["cleanup_errors"], [])
            self.assertFalse((root / "external/probe-hook-block").exists())
            branches = run("git", "branch", "--list", "plananvil/probe/*", cwd=repo).stdout.strip()
            self.assertEqual(branches, "")
            self.assertEqual(preflight(repo)["result"], "SOURCE_PREFLIGHT_PASSED")


if __name__ == "__main__":
    unittest.main()
