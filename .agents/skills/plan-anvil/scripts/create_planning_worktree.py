from __future__ import annotations

import argparse
import tempfile
from pathlib import Path
from typing import Any

from common import (
    PLAN_ID_RE,
    PlanAnvilError,
    cli_main,
    compare_snapshot,
    discover_repo,
    emit,
    git,
    load_json,
    make_run_id,
    repo_relative,
    require_external_path,
    slugify,
    source_snapshot,
)


def default_destination(source_repo: Path, plan_id: str, slug: str) -> Path:
    source_repo = source_repo.resolve()
    parent = source_repo.parent / f".{source_repo.name}-plananvil-worktrees"
    return parent / f"{plan_id}-{slug}"


def create_planning_worktree(
    source: Path,
    *,
    plan_id: str,
    slug: str,
    capability_report: dict[str, Any],
    destination: Path | None = None,
) -> dict[str, Any]:
    if not PLAN_ID_RE.fullmatch(plan_id):
        raise PlanAnvilError(f"Invalid plan id: {plan_id}", code="INVALID_PLAN_ID")
    slug = slugify(slug)
    if capability_report.get("result") != "GIT_READY" or not capability_report.get("ok"):
        raise PlanAnvilError("A successful complete Git capability report is required", code="GIT_NOT_READY")

    repo = discover_repo(source)
    expected_root = Path(capability_report["repository_root"]).resolve()
    if repo != expected_root:
        raise PlanAnvilError("Capability report belongs to a different repository", code="CAPABILITY_REPOSITORY_MISMATCH")

    snapshot = capability_report.get("source_snapshot")
    changed = compare_snapshot(repo, snapshot)
    if changed:
        raise PlanAnvilError(
            f"Source changed after Git capability verification: {', '.join(changed)}",
            code="SOURCE_CHANGED",
            details=changed,
        )

    base_sha = snapshot["head"]
    base_branch = capability_report.get("base_branch") or snapshot.get("branch")
    if not base_branch:
        raise PlanAnvilError("Base branch is unresolved", code="GIT_BASE_AMBIGUOUS")

    branch = f"pursue/plan/{plan_id}/{slug}"
    existing = git(repo, "show-ref", "--verify", f"refs/heads/{branch}", check=False)
    if existing.returncode == 0:
        raise PlanAnvilError(f"Planning branch already exists: {branch}", code="PLANNING_BRANCH_EXISTS")

    dest = require_external_path(
        repo,
        destination or default_destination(repo, plan_id, slug),
        code="PLANNING_WORKTREE_INSIDE_WORKTREE",
    )
    if dest.exists():
        raise PlanAnvilError(f"Planning worktree path already exists: {dest}", code="PLANNING_WORKTREE_EXISTS")
    dest.parent.mkdir(parents=True, exist_ok=True)

    add = git(repo, "worktree", "add", "-b", branch, str(dest), base_sha, check=False, timeout=180)
    if add.returncode != 0:
        raise PlanAnvilError(
            "Could not create planning branch and linked worktree",
            code="PLANNING_WORKTREE_CREATE_FAILED",
            details=add.stderr or add.stdout,
        )

    try:
        head = git(dest, "rev-parse", "HEAD").stdout.strip()
        current_branch = git(dest, "symbolic-ref", "--short", "HEAD").stdout.strip()
        if head != base_sha or current_branch != branch:
            raise PlanAnvilError("Planning worktree identity verification failed", code="PLANNING_WORKTREE_MISMATCH")

        changed = compare_snapshot(repo, snapshot)
        if changed:
            raise PlanAnvilError(
                f"Source changed while creating planning worktree: {', '.join(changed)}",
                code="SOURCE_CHANGED",
                details=changed,
            )
    except Exception:
        git(repo, "worktree", "remove", "--force", str(dest), check=False, timeout=180)
        git(repo, "branch", "-D", branch, check=False)
        raise

    run_id = make_run_id(plan_id, slug)
    return {
        "ok": True,
        "result": "PLANNING_WORKTREE_READY",
        "plan_id": plan_id,
        "run_id": run_id,
        "slug": slug,
        "source_repository": str(repo),
        "planning_worktree": str(dest),
        "planning_branch": branch,
        "base_branch": base_branch,
        "base_sha": base_sha,
        "source_snapshot": snapshot,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the isolated PlanAnvil planning branch and worktree")
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--plan-id", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--capability-report", type=Path, required=True)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    report = load_json(args.capability_report)
    payload = create_planning_worktree(
        args.source,
        plan_id=args.plan_id,
        slug=args.slug,
        capability_report=report,
        destination=args.destination,
    )
    return emit(payload)


if __name__ == "__main__":
    cli_main(main)
