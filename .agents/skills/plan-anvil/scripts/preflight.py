from __future__ import annotations

import argparse
import re
import shutil
import subprocess
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


MINIMUM_GIT_VERSION = (2, 30, 0)
_GIT_VERSION_RE = re.compile(
    r"\bgit\s+version\s+(\d+)\.(\d+)(?:\.(\d+))?",
    re.IGNORECASE,
)


def _format_version(version: tuple[int, int, int]) -> str:
    return ".".join(str(item) for item in version)


def parse_git_version(output: str) -> tuple[int, int, int] | None:
    match = _GIT_VERSION_RE.search(output.strip())
    if match is None:
        return None
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3) or 0),
    )


def _inspect_git_version() -> dict[str, Any]:
    minimum = _format_version(MINIMUM_GIT_VERSION)
    try:
        result = subprocess.run(
            ["git", "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "ok": False,
            "detected": None,
            "minimum": minimum,
            "diagnostic": f"Could not execute git --version: {exc}",
        }

    raw = (result.stdout or result.stderr).strip()
    if result.returncode != 0:
        return {
            "ok": False,
            "detected": None,
            "minimum": minimum,
            "diagnostic": f"git --version failed with exit code {result.returncode}: {raw}",
        }

    parsed = parse_git_version(raw)
    if parsed is None:
        return {
            "ok": False,
            "detected": None,
            "minimum": minimum,
            "diagnostic": f"Could not parse Git version output: {raw!r}",
        }

    detected = _format_version(parsed)
    if parsed < MINIMUM_GIT_VERSION:
        return {
            "ok": False,
            "detected": detected,
            "minimum": minimum,
            "diagnostic": f"Git {detected} is below the required minimum {minimum}.",
        }
    return {
        "ok": True,
        "detected": detected,
        "minimum": minimum,
        "diagnostic": None,
    }


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

    version = _inspect_git_version()
    if not version["ok"]:
        result = "GIT_UNAVAILABLE"
        return {
            "ok": False,
            "result": result,
            "plan_status": plan_status_for(result),
            "git_version": version["detected"],
            "minimum_git_version": version["minimum"],
            "diagnostic": version["diagnostic"],
        }

    try:
        repo = discover_repo(source)
    except PlanAnvilError:
        result = "NOT_A_GIT_REPOSITORY"
        return {
            "ok": False,
            "result": result,
            "plan_status": plan_status_for(result),
            "git_version": version["detected"],
            "minimum_git_version": version["minimum"],
        }

    head_result = git(repo, "rev-parse", "--verify", "HEAD", check=False)
    if head_result.returncode != 0:
        result = "GIT_BASE_AMBIGUOUS"
        return {
            "ok": False,
            "result": result,
            "plan_status": plan_status_for(result),
            "repository_root": str(repo),
            "git_version": version["detected"],
            "minimum_git_version": version["minimum"],
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
        "git_version": version["detected"],
        "minimum_git_version": version["minimum"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only PlanAnvil source preflight")
    add_source_argument(parser)
    args = parser.parse_args()
    payload = preflight(args.source)
    return emit(payload, exit_code=0 if payload["ok"] else 2)


if __name__ == "__main__":
    cli_main(main)
