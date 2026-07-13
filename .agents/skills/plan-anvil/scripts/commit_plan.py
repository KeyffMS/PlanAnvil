from __future__ import annotations

import argparse
import fnmatch
from pathlib import Path
from typing import Any

from common import (
    PlanAnvilError,
    atomic_write_text,
    cli_main,
    compare_snapshot,
    discover_repo,
    emit,
    git,
    load_json,
    repo_relative,
)
from transition_state import transition_state
from validate_all import validate_all


def _staged_paths(repo: Path) -> list[str]:
    result = git(repo, "diff", "--cached", "--name-only", "-z", "--")
    return sorted(item for item in result.stdout.split("\0") if item)


def _allowed(path: str, run_rel: str) -> bool:
    patterns = [".gitignore", ".pursue/SYSTEM_PROFILE.md", f"{run_rel}/**"]
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _commit(repo: Path, message: str) -> str:
    result = git(repo, "commit", "-m", message, check=False, timeout=180)
    if result.returncode != 0:
        raise PlanAnvilError(
            f"Git commit failed: {message}",
            code="PLAN_COMMIT_FAILED",
            details={"stdout": result.stdout, "stderr": result.stderr},
        )
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def _verify_planning_identity(repo: Path, manifest: dict[str, Any]) -> None:
    expected_branch = manifest["repository"]["planning_branch"]
    actual_branch = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False).stdout.strip()
    if actual_branch != expected_branch:
        raise PlanAnvilError(
            f"Planning branch changed: expected {expected_branch}, found {actual_branch or 'detached HEAD'}",
            code="PLANNING_BRANCH_MISMATCH",
        )
    base_sha = manifest["repository"]["base_sha"]
    ancestor = git(repo, "merge-base", "--is-ancestor", base_sha, "HEAD", check=False)
    if ancestor.returncode != 0:
        raise PlanAnvilError("Planning branch no longer descends from the recorded base SHA", code="BASE_SHA_MISMATCH")


def commit_plan(
    planning: Path,
    run_root: Path,
    *,
    source: Path | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    repo = discover_repo(planning)
    run = (run_root if run_root.is_absolute() else repo / run_root).resolve()
    manifest = load_json(run / "manifest.json")
    local_state = load_json(run / "local-state.json")
    state_path = run / "state.json"
    state = load_json(state_path)
    if state.get("status") != "COMPARISON_VALID":
        raise PlanAnvilError(
            f"Commit requires COMPARISON_VALID, found {state.get('status')}",
            code="INVALID_STATE_FOR_COMMIT",
        )

    _verify_planning_identity(repo, manifest)
    final_validation = validate_all(repo, run, source=source, phase="final", advance_state=False)
    if not final_validation["ok"]:
        raise PlanAnvilError("Final validation failed", code="PLAN_VALIDATION_FAILED", details=final_validation["findings"])

    source_repo = discover_repo(source) if source else Path(local_state["paths"]["source_worktree"])
    changed = compare_snapshot(source_repo, local_state["source_snapshot"])
    if changed:
        raise PlanAnvilError("Source worktree changed before commit", code="SOURCE_CHANGED", details=changed)

    run_rel = repo_relative(repo, run)
    git(repo, "add", "--", ".gitignore", ".pursue/SYSTEM_PROFILE.md", run_rel)
    staged = _staged_paths(repo)
    forbidden = [
        ".pursue/SYSTEM_PROFILE.local.md",
        f"{run_rel}/local-state.json",
        f"{run_rel}/.generation-lock",
        f"{run_rel}/.execution-lock",
    ]
    bad = [
        path for path in staged
        if not _allowed(path, run_rel) or any(fnmatch.fnmatchcase(path, item) for item in forbidden)
    ]
    if bad:
        raise PlanAnvilError("Staged paths violate the planning allowlist", code="STAGED_PATH_VIOLATION", details=bad)
    if not staged:
        raise PlanAnvilError("No planning artifacts are staged", code="NOTHING_TO_COMMIT")

    plan_id = manifest["plan_id"]
    _verify_planning_identity(repo, manifest)
    plan_commit = _commit(repo, message or f"Add PlanAnvil plan {plan_id}")

    # Advance canonical state only after Git proves the plan commit exists.
    current_state = load_json(state_path)
    transition_state(
        state_path,
        expected_revision=current_state["revision"],
        new_status="PLAN_COMMITTED",
        phase="COMMIT_PLANNING_ARTIFACTS",
        next_action_type="WRITE_FINAL_REPORT",
        next_action_target="final/REPORT.md",
        hash_paths=[
            run / "PLAN.md",
            run / "traceability.json",
            run / "reports/validation/summary.json",
            run / "reports/plan-review/blind-review.md",
            run / "reports/plan-review/blind-review.json",
            run / "reports/plan-review/comparison.json",
        ],
    )

    comparison = load_json(run / "reports/plan-review/comparison.json")
    report = f"""# PlanAnvil Final Report

- Status: `PLAN_READY`
- Planning branch: `{manifest['repository']['planning_branch']}`
- Planning commit: `{plan_commit}`
- Plan: `{run_rel}/PLAN.md`
- Deterministic validation: `PASS`
- Blind review: `PASS`
- Comparison: `{comparison['result']}`

## Assumptions and unknowns

See `PLAN.md`. Any recorded non-critical unknown remains subject to its stated verification step. Critical unknowns are not permitted in a ready plan.

## Next run

Use the separate execution-run prompt in `PLAN.md`. Reconcile the manifest, canonical state, ignored local state, profiles, latest valid checkpoint, and Git state before executing only the next approved action.

No implementation was executed. Start a separate Codex run using the execution prompt in PLAN.md.
"""
    report_path = run / "final/REPORT.md"
    atomic_write_text(report_path, report)

    current_state = load_json(state_path)
    transition_state(
        state_path,
        expected_revision=current_state["revision"],
        new_status="STOPPED",
        phase="REPORT_AND_STOP",
        next_action_type="NONE",
        next_action_target=None,
        hash_paths=[report_path],
    )
    git(repo, "add", "--", repo_relative(repo, state_path), repo_relative(repo, report_path))
    staged_final = _staged_paths(repo)
    bad_final = [path for path in staged_final if not _allowed(path, run_rel)]
    if bad_final:
        raise PlanAnvilError("Final staged paths violate allowlist", code="STAGED_PATH_VIOLATION", details=bad_final)
    _verify_planning_identity(repo, manifest)
    final_commit = _commit(repo, f"Finalize PlanAnvil plan {plan_id}")

    status = git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout
    if status:
        raise PlanAnvilError("Planning worktree is not clean after final commit", code="PLANNING_WORKTREE_DIRTY", details=status)
    changed = compare_snapshot(source_repo, local_state["source_snapshot"])
    if changed:
        raise PlanAnvilError("Source worktree changed during commit", code="SOURCE_CHANGED", details=changed)

    return {
        "ok": True,
        "result": "STOPPED",
        "status": "PLAN_READY",
        "planning_branch": manifest["repository"]["planning_branch"],
        "plan_commit": plan_commit,
        "final_commit": final_commit,
        "plan": f"{run_rel}/PLAN.md",
        "final_report": f"{run_rel}/final/REPORT.md",
        "pushed": False,
        "implementation_executed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and commit only approved PlanAnvil planning artifacts")
    parser.add_argument("--planning", type=Path, default=Path.cwd())
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--message")
    args = parser.parse_args()
    return emit(commit_plan(args.planning, args.run_root, source=args.source, message=args.message))


if __name__ == "__main__":
    cli_main(main)
