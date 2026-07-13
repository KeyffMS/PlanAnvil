from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from _helpers import init_repo, run
from common import atomic_write_json, load_json
from commit_plan import _recover_committed_finalization
from finalize_instruction_context import finalize_instruction_context
from scaffold_transaction import begin_scaffold_transaction
from schema_validator import validate
from test_git_capabilities import _classify_failure
from validate_artifacts import _extended_privacy_findings
from validate_plan_contract import validate_plan_contract
from validate_schema_coverage import validate_schema_coverage
from validate_traceability import validate_traceability

ROOT = Path(__file__).resolve().parents[4]
HOOKS = ROOT / ".codex/hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from plan_anvil_hooklib import ActiveRun, active_run_for_event


class AuditClosureTests(unittest.TestCase):
    def test_hook_selects_only_run_from_event_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worktree_a = root / "a"
            worktree_b = root / "b"
            run_a = ActiveRun(worktree_a, worktree_a / ".pursue/runs/run-a", {"mode": "PLAN_GENERATION"})
            run_b = ActiveRun(worktree_b, worktree_b / ".pursue/runs/run-b", {"mode": "PLAN_GENERATION"})
            with patch("plan_anvil_hooklib.git_root", return_value=worktree_a), patch(
                "plan_anvil_hooklib.active_runs", return_value=[run_a, run_b]
            ):
                selected = active_run_for_event({"cwd": str(worktree_a)})
            self.assertEqual(selected, run_a)

    def test_hook_requires_explicit_id_for_ambiguous_worktree_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            worktree = Path(directory)
            first = ActiveRun(worktree, worktree / ".pursue/runs/run-a", {"mode": "PLAN_GENERATION"})
            second = ActiveRun(worktree, worktree / ".pursue/runs/run-b", {"mode": "PLAN_GENERATION"})
            with patch("plan_anvil_hooklib.git_root", return_value=worktree), patch(
                "plan_anvil_hooklib.active_runs", return_value=[first, second]
            ):
                self.assertIsNone(active_run_for_event({"cwd": str(worktree)}))
                selected = active_run_for_event(
                    {"cwd": str(worktree), "plananvil_run_id": "run-b"}
                )
            self.assertEqual(selected, second)

    def test_traceability_rejects_cross_stage_criterion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = init_repo(Path(directory) / "repo")
            run_root = repo / ".pursue/runs/run"
            run_root.mkdir(parents=True)
            atomic_write_json(
                run_root / "traceability.json",
                {
                    "schema_version": "1.1.0",
                    "requirements": [
                        {
                            "id": "REQ-01-01",
                            "text": "Requirement",
                            "critical": True,
                            "stages": ["STAGE-01"],
                            "criteria": ["AC-02-01"],
                        }
                    ],
                    "criteria": [
                        {
                            "id": "AC-02-01",
                            "stage": "STAGE-02",
                            "risks": [],
                            "controls": ["CTRL-02-01"],
                            "evidence_type": "AUTOMATED_TEST",
                            "evidence": [],
                        }
                    ],
                    "controls": [],
                    "gaps": [],
                },
            )
            result = validate_traceability(repo, run_root, write_report=False)
            self.assertFalse(result["ok"])
            self.assertEqual(result["findings"][0]["kind"], "requirement-criterion-stage-mismatch")

    def test_schema_coverage_rejects_unknown_json_role(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = init_repo(Path(directory) / "repo")
            run_root = repo / ".pursue/runs/run"
            unknown = run_root / "evidence/unknown.json"
            unknown.parent.mkdir(parents=True)
            atomic_write_json(unknown, {"schema_version": "1.1.0"})
            result = validate_schema_coverage(repo, run_root, write_report=False)
            self.assertFalse(result["ok"])
            self.assertIn(
                {"kind": "missing-versioned-schema", "path": "evidence/unknown.json"},
                result["findings"],
            )

    def test_non_behavior_stage_may_use_equivalent_cycle_without_red(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = init_repo(Path(directory) / "repo")
            run_root = repo / ".pursue/runs/run"
            stage = run_root / "stages/STAGE-01.md"
            stage.parent.mkdir(parents=True)
            stage.write_text("stage\n", encoding="utf-8")
            base_result = {
                "ok": False,
                "result": "FAIL",
                "findings": [
                    {
                        "kind": "stage-evidence-cycle-incomplete",
                        "stage": "STAGE-01",
                        "missing": "RED",
                    }
                ],
                "plan_status": "PLAN_READY",
            }
            with patch("validate_plan_contract.validate_plan", return_value=base_result), patch(
                "validate_plan_contract._frontmatter",
                return_value={"stage_id": "STAGE-01", "classification": "DOCUMENTATION"},
            ):
                result = validate_plan_contract(repo, run_root, write_report=False)
            self.assertTrue(result["ok"])

    def test_public_repository_urls_do_not_trigger_privacy_findings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = init_repo(Path(directory) / "repo")
            report = repo / "report.md"
            report.write_text(
                "https://github.com/openai/openai\ngit@github.com:openai/openai.git\n",
                encoding="utf-8",
            )
            self.assertEqual(_extended_privacy_findings(repo, [report]), [])
            report.write_text("https://user:password@localhost/private.git\n", encoding="utf-8")
            findings = _extended_privacy_findings(repo, [report])
            self.assertEqual(findings[0]["kind"], "private-repository-url")

    def test_review_schema_requires_independent_author_role(self) -> None:
        schema = load_json(ROOT / ".agents/skills/plan-anvil/schemas/review.schema.json")
        digest = "sha256:" + "0" * 64
        payload = {
            "schema_version": "1.1.0",
            "report_type": "BLIND_PLAN_REVIEW",
            "created_at": "2026-01-01T00:00:00Z",
            "inputs": {"PLAN.md": digest},
            "result": "PASS",
            "findings": [],
            "markdown_hash": digest,
        }
        self.assertTrue(validate(payload, schema))
        payload["author_role"] = "plan-anvil-reviewer"
        self.assertEqual(validate(payload, schema), [])

    def test_git_failure_classifier_uses_actual_hook_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = init_repo(Path(directory) / "repo")
            self.assertEqual(
                _classify_failure("fatal: unrelated commit failure", operation="commit", repo=repo),
                "GIT_WRITE_RESTRICTED",
            )
            self.assertEqual(
                _classify_failure("pre-commit hook failed", operation="commit", repo=repo),
                "GIT_HOOK_BLOCKED",
            )

    def test_scaffold_transaction_publishes_complete_directory_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / "runs"
            final = parent / "run"
            identity = {
                "plan_id": "PG-20260101-000000-ABCD",
                "run_id": "run",
                "base_sha": "0" * 40,
                "planning_branch": "main",
                "goal_hash": "sha256:" + "1" * 64,
            }
            transaction = begin_scaffold_transaction(final, identity)
            self.assertIsNotNone(transaction)
            assert transaction is not None
            required = [
                "state.json",
                "compliance.json",
                "traceability.json",
                "local-state.json",
                "PLAN.md",
                "evidence/original-goal.md",
                "evidence/git-capability.json",
                "evidence/lifecycle.json",
            ]
            manifest = {
                "plan_id": identity["plan_id"],
                "run_id": identity["run_id"],
                "repository": {
                    "base_sha": identity["base_sha"],
                    "planning_branch": identity["planning_branch"],
                },
            }
            atomic_write_json(transaction.build_root / "manifest.json", manifest)
            for relative in required:
                path = transaction.build_root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n" if path.suffix == ".json" else "x\n", encoding="utf-8")
            transaction.publish()
            self.assertTrue(final.is_dir())
            self.assertIsNone(begin_scaffold_transaction(final, identity))

    def test_finalization_recovers_existing_stopped_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = init_repo(Path(directory) / "repo")
            run_root = repo / ".pursue/runs/run"
            report = run_root / "final/REPORT.md"
            report.parent.mkdir(parents=True)
            report.write_text("final\n", encoding="utf-8")
            stopped = {
                "schema_version": "1.1.0",
                "revision": 2,
                "updated_at": "2026-01-01T00:00:00Z",
                "mode": "PLAN_GENERATION",
                "status": "STOPPED",
                "current_stage": None,
                "current_phase": "REPORT_AND_STOP",
                "next_action": {"type": "NONE", "target": None},
                "last_checkpoint": None,
                "open_blockers": [],
                "artifact_hashes": {},
            }
            atomic_write_json(run_root / "state.json", stopped)
            run("git", "add", ".", cwd=repo)
            run("git", "commit", "-m", "final", cwd=repo)
            working = {**stopped, "revision": 1, "status": "PLAN_COMMITTED"}
            atomic_write_json(run_root / "state.json", working)
            result = _recover_committed_finalization(
                repo,
                run_root,
                {"repository": {"planning_branch": "main"}},
                working,
            )
            self.assertIsNotNone(result)
            self.assertEqual(load_json(run_root / "state.json")["status"], "STOPPED")

    def test_instruction_context_updates_stage_bindings_and_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = init_repo(Path(directory) / "repo")
            pursue = repo / ".pursue"
            pursue.mkdir()
            profile = pursue / "SYSTEM_PROFILE.md"
            profile.write_text(
                "# PlanAnvil Repository Profile\n\n## Project instruction map\n\nPending explicit instruction mapping.\n\n## Next\n",
                encoding="utf-8",
            )
            run_root = repo / ".pursue/runs/run"
            instruction = run_root / "evidence/instruction-map.json"
            instruction.parent.mkdir(parents=True)
            digest = "sha256:" + "2" * 64
            atomic_write_json(
                instruction,
                {
                    "schema_version": "1.1.0",
                    "generated_at": "2026-01-01T00:00:00Z",
                    "affected_paths": ["src/app.py"],
                    "fallback_filenames": [],
                    "automatic_byte_limit": 32768,
                    "files": [
                        {
                            "path": "AGENTS.md",
                            "sha256": digest,
                            "bytes": 10,
                            "full_read": True,
                            "scope": ".",
                            "precedence": 0,
                            "affected_paths": ["src/app.py"],
                            "truncation_risk": False,
                            "safety_critical_rules": [],
                        }
                    ],
                    "conflicts": [],
                },
            )
            stage = run_root / "stages/STAGE-01.md"
            stage.parent.mkdir(parents=True)
            stage.write_text(
                "---\nschema_version: '1.1.0'\nstage_id: 'STAGE-01'\napplicable_instructions: "
                f"[{{'path': 'AGENTS.md', 'sha256': '{digest}'}}]\n---\nstage\n",
                encoding="utf-8",
            )
            finalize_instruction_context(repo, run_root)
            updated = load_json(instruction)
            self.assertEqual(updated["files"][0]["affected_stages"], ["STAGE-01"])
            self.assertNotIn("Pending explicit instruction mapping", profile.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
