from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Any

from common import (
    PlanAnvilError,
    add_source_argument,
    cli_main,
    detect_git_operation,
    discover_repo,
    emit,
    git,
    source_snapshot,
)


def resolve_base(repo: Path) -> tuple[str | None, str | None]:
    attached = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    if attached.returncode == 0:
        branch = attached.stdout.strip()
        return branch, None
    candidates = [
        line.strip()
        for line in git(repo, "for-each-ref", "--format=%(refname:short)", "--contains=HEAD", "refs/heads").stdout.splitlines()
        if line.strip()
    ]
    if len(candidates) == 1:
        return candidates[0], None
    return None, "GIT_BASE_AMBIGUOUS"


def plan_status_for(result: str) -> str | None:
    if result == "SOURCE_PREFLIGHT_PASSED":
        return None
    if result in {"GIT_DIRTY", "GIT_OPERATION_IN_PROGRESS", "GIT_BASE_AMBIGUOUS"}:
        return "BLOCKED_BY_GIT_STATE"
    if result in {"GIT_READ_ONLY", "GIT_WRITE_RESTRICTED"}:
        return "BLOCKED_BY_GIT_PERMISSIONS"
    return "BLOCKED_BY_RUNTIME_PREREQUISITE"


def preflight(source: Path) -> dict[str, Any]:
    if shutil.which("git") is None:
        result = "GIT_UNAVAILABLE"
        return {"ok": False, "result": result, "plan_status": plan_status_for(result)}

    try:
        repo = discover_repo(source)
    except PlanAnvilError:
        result = "NOT_A_GIT_REPOSITORY"
        return {"ok": False, "result": result, "plan_status": plan_status_for(result)}

    head_result = git(repo, "rev-parse", "--verify", "HEAD", check=False)
    if head_result.returncode != 0:
        result = "GIT_BASE_AMBIGUOUS"
        return {
            "ok": False,
            "result": result,
            "plan_status": plan_status_for(result),
            "repository_root": str(repo),
            "diagnostic": head_result.stderr.strip(),
        }

    status_raw = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
    conflicts = [
        item for item in git(repo, "diff", "--name-only", "--diff-filter=U", "-z").stdout.split("\0") if item
    ]
    operation = detect_git_operation(repo)
    base_branch, base_error = resolve_base(repo)
    worktrees = git(repo, "worktree", "list", "--porcelain", check=False)

    if status_raw or conflicts:
        result = "GIT_DIRTY"
    elif operation:
        result = "GIT_OPERATION_IN_PROGRESS"
    elif base_error:
        result = base_error
    elif worktrees.returncode != 0:
        result = "GIT_WORKTREE_UNSUPPORTED"
    else:
        result = "SOURCE_PREFLIGHT_PASSED"

    snapshot = source_snapshot(repo)
    return {
        "ok": result == "SOURCE_PREFLIGHT_PASSED",
        "result": result,
        "plan_status": plan_status_for(result),
        "repository_root": str(repo),
        "head": snapshot["head"],
        "branch": snapshot["branch"],
        "base_branch": base_branch,
        "clean": not bool(status_raw),
        "conflicts": conflicts,
        "operation": operation,
        "worktrees": worktrees.stdout if worktrees.returncode == 0 else None,
        "source_snapshot": snapshot,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only PlanAnvil source preflight")
    add_source_argument(parser)
    args = parser.parse_args()
    payload = preflight(args.source)
    return emit(payload, exit_code=0 if payload["ok"] else 2)


if __name__ == "__main__":
    cli_main(main)
