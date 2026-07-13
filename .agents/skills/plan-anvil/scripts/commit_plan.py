from __future__ import annotations

import argparse
import fnmatch
import tempfile
from pathlib import Path
from typing import Any

from common import (
    PlanAnvilError,
    atomic_write_json,
    atomic_write_text,
    canonical_json_text,
    cli_main,
    compare_snapshot,
    discover_repo,
    emit,
    git,
    load_json,
    repo_relative,
    sha256_file,
    utc_now,
)
from schema_validator import assert_valid_file, validate
from transition_state import run_lock, transition_state
from validate_all import validate_all


def _staged_paths(repo: Path) -> list[str]:
    result = git(repo, "diff", "--cached", "--name-only", "-z", "--")
    return sorted(item for item in result.stdout.split("\0") if item)


def _run_allowlist(run_rel: str) -> list[str]:
    return [
        f"{run_rel}/PLAN.md",
        f"{run_rel}/manifest.json",
        f"{run_rel}/state.json",
        f"{run_rel}/compliance.json",
        f"{run_rel}/traceability.json",
        f"{run_rel}/stages/STAGE-*.md",
        f"{run_rel}/checkpoints/CHECKPOINT-*.json",
        f"{run_rel}/risks/RISK-*.json",
        f"{run_rel}/evidence/*.md",
        f"{run_rel}/evidence/*.json",
        f"{run_rel}/reports/**/*.md",
        f"{run_rel}/reports/**/*.json",
        f"{run_rel}/diffs/*.json",
        f"{run_rel}/logs/*.json",
        f"{run_rel}/incidents/*.md",
        f"{run_rel}/incidents/*.json",
        f"{run_rel}/final/REPORT.md",
        f"{run_rel}/final/*.json",
    ]


def _forbidden_patterns(run_rel: str) -> list[str]:
    return [
        ".pursue/SYSTEM_PROFILE.local.md",
        f"{run_rel}/local-state.json",
        f"{run_rel}/.generation-lock",
        f"{run_rel}/.execution-lock",
        f"{run_rel}/**/*.py",
        f"{run_rel}/**/*.php",
        f"{run_rel}/**/*.js",
        f"{run_rel}/**/*.ts",
        f"{run_rel}/**/*.sh",
        f"{run_rel}/**/*.ps1",
        f"{run_rel}/**/*.exe",
        f"{run_rel}/**/*.dll",
        f"{run_rel}/**/*.so",
    ]


def _allowed(path: str, run_rel: str) -> bool:
    allowed = [".gitignore", ".pursue/SYSTEM_PROFILE.md", *_run_allowlist(run_rel)]
    forbidden = _forbidden_patterns(run_rel)
    return (
        any(fnmatch.fnmatchcase(path, pattern) for pattern in allowed)
        and not any(fnmatch.fnmatchcase(path, pattern) for pattern in forbidden)
    )


def _assert_staged_allowlist(repo: Path, run_rel: str) -> list[str]:
    staged = _staged_paths(repo)
    bad = [path for path in staged if not _allowed(path, run_rel)]
    if bad:
        raise PlanAnvilError(
            "Staged paths violate the planning allowlist",
            code="STAGED_PATH_VIOLATION",
            details=bad,
        )
    return staged


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


def _prepare_stopped_state(state_path: Path, report_path: Path) -> dict[str, Any]:
    current = load_json(state_path)
    if current.get("status") != "PLAN_COMMITTED":
        raise PlanAnvilError(
            f"Finalization requires PLAN_COMMITTED, found {current.get('status')}",
            code="INVALID_STATE_FOR_FINALIZATION",
        )
    artifact_hashes = dict(current.get("artifact_hashes", {}))
    artifact_hashes[report_path.relative_to(state_path.parent).as_posix()] = sha256_file(report_path)
    replacement = {
        **current,
        "revision": current["revision"] + 1,
        "updated_at": utc_now(),
        "status": "STOPPED",
        "current_phase": "REPORT_AND_STOP",
        "next_action": {"type": "NONE", "target": None},
        "artifact_hashes": artifact_hashes,
    }
    schema_path = Path(__file__).resolve().parent.parent / "schemas/state.schema.json"
    errors = validate(replacement, load_json(schema_path))
    if errors:
        raise PlanAnvilError(
            "Prepared STOPPED state failed schema validation",
            code="SCHEMA_VALIDATION_FAILED",
            details=errors,
        )
    return replacement


def _stage_json_blob(repo: Path, relative_path: str, payload: dict[str, Any]) -> str:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix="plananvil-state-",
            suffix=".json",
            delete=False,
        ) as handle:
            handle.write(canonical_json_text(payload))
            handle.flush()
            temporary = Path(handle.name)
        blob = git(repo, "hash-object", "-w", str(temporary)).stdout.strip()
        git(repo, "update-index", "--add", "--cacheinfo", "100644", blob, relative_path)
        return blob
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _commit_plan_locked(
    repo: Path,
    run: Path,
    manifest: dict[str, Any],
    local_state: dict[str, Any],
    *,
    source: Path | None,
    message: str | None,
) -> dict[str, Any]:
    state_path = run / "state.json"
    state = load_json(state_path)
    if state.get("status") not in {"COMPARISON_VALID", "PLAN_COMMITTED"}:
        raise PlanAnvilError(
            f"Commit requires COMPARISON_VALID or PLAN_COMMITTED, found {state.get('status')}",
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
    plan_id = manifest["plan_id"]

    if state.get("status") == "COMPARISON_VALID":
        git(repo, "add", "--", ".gitignore", ".pursue/SYSTEM_PROFILE.md", run_rel)
        staged = _assert_staged_allowlist(repo, run_rel)
        if not staged:
            raise PlanAnvilError("No planning artifacts are staged", code="NOTHING_TO_COMMIT")

        _verify_planning_identity(repo, manifest)
        plan_commit = _commit(repo, message or f"Add PlanAnvil plan {plan_id}")
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
            lock_held=True,
        )
    else:
        plan_commit = git(repo, "rev-parse", "HEAD").stdout.strip()

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

    stopped_state = _prepare_stopped_state(state_path, report_path)
    state_rel = repo_relative(repo, state_path)
    report_rel = repo_relative(repo, report_path)
    git(repo, "add", "--", report_rel)
    _stage_json_blob(repo, state_rel, stopped_state)

    _assert_staged_allowlist(repo, run_rel)
    _verify_planning_identity(repo, manifest)
    try:
        final_commit = _commit(repo, f"Finalize PlanAnvil plan {plan_id}")
    except Exception:
        git(repo, "add", "--", state_rel)
        raise

    atomic_write_json(state_path, stopped_state)
    state_schema = Path(__file__).resolve().parent.parent / "schemas/state.schema.json"
    assert_valid_file(state_path, state_schema)

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
    with run_lock(state_path, command="commit-plan"):
        return _commit_plan_locked(
            repo,
            run,
            manifest,
            local_state,
            source=source,
            message=message,
        )


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
