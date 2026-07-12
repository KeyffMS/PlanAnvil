from __future__ import annotations

import argparse
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from common import PlanAnvilError, add_source_argument, cli_main, compare_snapshot, emit, git, require_external_path, source_snapshot
from preflight import plan_status_for, preflight


class _ProbeAbort(Exception):
    pass


def _classify_failure(stderr: str, *, operation: str, repo: Path) -> str:
    text = stderr.lower()
    if any(token in text for token in ["author identity unknown", "unable to auto-detect email", "please tell me who you are"]):
        return "GIT_IDENTITY_MISSING"
    if any(token in text for token in ["gpg failed to sign", "signing failed", "failed to sign", "ssh signing"]):
        return "GIT_SIGNING_BLOCKED"
    if any(token in text for token in ["permission denied", "operation not permitted", "read-only file system", "cannot lock ref"]):
        return "GIT_WRITE_RESTRICTED"
    if operation == "worktree":
        return "GIT_WORKTREE_UNSUPPORTED"
    if operation == "commit":
        hooks_dir = Path(git(repo, "rev-parse", "--git-path", "hooks").stdout.strip())
        if not hooks_dir.is_absolute():
            hooks_dir = repo / hooks_dir
        relevant = ["pre-commit", "prepare-commit-msg", "commit-msg", "post-commit"]
        if any((hooks_dir / name).exists() for name in relevant):
            return "GIT_HOOK_BLOCKED"
        return "GIT_WRITE_RESTRICTED"
    return "GIT_WRITE_RESTRICTED"


def _run(repo: Path, operation: str, *args: str, cwd: Path | None = None) -> tuple[bool, str, str | None]:
    target = cwd or repo
    result = git(target, *args, check=False)
    if result.returncode == 0:
        return True, result.stdout, None
    return False, result.stderr or result.stdout, _classify_failure(result.stderr + result.stdout, operation=operation, repo=repo)


def probe_git_capabilities(source: Path, run_id: str, temp_parent: Path | None = None) -> dict[str, Any]:
    initial = preflight(source)
    if not initial["ok"]:
        return initial

    repo = Path(initial["repository_root"])
    before = source_snapshot(repo)
    safe_run = re.sub(r"[^A-Za-z0-9._-]+", "-", run_id).strip("-")[:80]
    if not safe_run:
        raise PlanAnvilError("Run id is empty after normalization", code="INVALID_RUN_ID")

    ref_name = f"refs/plananvil/probes/{safe_run}"
    branch_name = f"plananvil/probe/{safe_run}"
    parent = require_external_path(
        repo,
        temp_parent or Path(tempfile.gettempdir()) / "plananvil-probes",
        code="PROBE_TEMP_INSIDE_WORKTREE",
    )
    parent.mkdir(parents=True, exist_ok=True)
    probe_path = parent / safe_run
    if probe_path.exists():
        raise PlanAnvilError(f"Probe path already exists: {probe_path}", code="PROBE_PATH_EXISTS")

    steps: list[dict[str, Any]] = []
    created_ref = False
    created_branch = False
    created_worktree = False
    primary_result = "GIT_READY"
    cleanup_errors: list[str] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        steps.append({"step": name, "ok": ok, "detail": detail.strip()[:2000]})

    try:
        ok, detail, failure = _run(repo, "ref", "update-ref", ref_name, before["head"])
        record("create_temporary_ref", ok, detail)
        if not ok:
            primary_result = failure or "GIT_WRITE_RESTRICTED"
            raise _ProbeAbort
        created_ref = True

        verify = git(repo, "rev-parse", ref_name, check=False)
        ok = verify.returncode == 0 and verify.stdout.strip() == before["head"]
        record("verify_temporary_ref", ok, verify.stderr or verify.stdout)
        if not ok:
            primary_result = "GIT_WRITE_RESTRICTED"
            raise _ProbeAbort

        delete_ref = git(repo, "update-ref", "-d", ref_name, check=False)
        ok = delete_ref.returncode == 0
        record("delete_temporary_ref", ok, delete_ref.stderr)
        if not ok:
            primary_result = "GIT_WRITE_RESTRICTED"
            raise _ProbeAbort
        created_ref = False

        branch = git(repo, "branch", branch_name, before["head"], check=False)
        ok = branch.returncode == 0
        record("create_probe_branch", ok, branch.stderr)
        if not ok:
            primary_result = _classify_failure(branch.stderr, operation="branch", repo=repo)
            raise _ProbeAbort
        created_branch = True

        worktree = git(repo, "worktree", "add", "--no-checkout", str(probe_path), branch_name, check=False, timeout=180)
        ok = worktree.returncode == 0
        record("create_probe_worktree", ok, worktree.stderr or worktree.stdout)
        if not ok:
            primary_result = _classify_failure(worktree.stderr, operation="worktree", repo=repo)
            raise _ProbeAbort
        created_worktree = True

        checkout = git(probe_path, "checkout", "--detach", branch_name, check=False)
        ok = checkout.returncode == 0
        record("checkout_probe_worktree", ok, checkout.stderr or checkout.stdout)
        if not ok:
            primary_result = "GIT_WORKTREE_UNSUPPORTED"
            raise _ProbeAbort

        probe_file = probe_path / f".plananvil-probe-{safe_run}"
        probe_file.write_text("PlanAnvil Git capability probe\n", encoding="utf-8", newline="\n")
        record("create_probe_file", probe_file.exists())

        add = git(probe_path, "add", "--", probe_file.name, check=False)
        ok = add.returncode == 0
        record("update_probe_index", ok, add.stderr)
        if not ok:
            primary_result = _classify_failure(add.stderr, operation="index", repo=repo)
            raise _ProbeAbort

        commit = git(
            probe_path,
            "commit",
            "-m",
            f"PlanAnvil capability probe {safe_run}",
            check=False,
            timeout=180,
        )
        ok = commit.returncode == 0
        record("create_probe_commit", ok, commit.stderr or commit.stdout)
        if not ok:
            primary_result = _classify_failure(commit.stderr + commit.stdout, operation="commit", repo=repo)
            raise _ProbeAbort

        clean = git(probe_path, "status", "--porcelain=v1", check=False)
        ok = clean.returncode == 0 and clean.stdout == ""
        record("verify_probe_clean", ok, clean.stderr or clean.stdout)
        if not ok:
            primary_result = "GIT_WRITE_RESTRICTED"
            raise _ProbeAbort

    except _ProbeAbort:
        pass
    finally:
        if created_ref:
            result = git(repo, "update-ref", "-d", ref_name, check=False)
            if result.returncode != 0:
                cleanup_errors.append(f"temporary ref: {result.stderr.strip()}")
        if created_worktree:
            result = git(repo, "worktree", "remove", "--force", str(probe_path), check=False, timeout=180)
            if result.returncode != 0:
                cleanup_errors.append(f"worktree: {result.stderr.strip()}")
            else:
                created_worktree = False
        if probe_path.exists() and not created_worktree:
            try:
                probe_path.rmdir()
            except OSError:
                cleanup_errors.append(f"probe directory remains: {probe_path}")
        if created_branch:
            result = git(repo, "branch", "-D", branch_name, check=False)
            if result.returncode != 0:
                cleanup_errors.append(f"branch: {result.stderr.strip()}")

    return _finish(repo, before, primary_result, steps, cleanup_errors)


def _finish(
    repo: Path,
    before: dict[str, Any],
    result: str,
    steps: list[dict[str, Any]],
    cleanup_errors: list[str],
) -> dict[str, Any]:
    changed = compare_snapshot(repo, before)
    if cleanup_errors or changed:
        result = "GIT_WRITE_RESTRICTED"
    refreshed = preflight(repo)
    return {
        "ok": result == "GIT_READY",
        "result": result,
        "plan_status": None if result == "GIT_READY" else plan_status_for(result),
        "repository_root": str(repo),
        "base_branch": refreshed.get("base_branch"),
        "source_snapshot": before,
        "source_snapshot_changed": changed,
        "cleanup_errors": cleanup_errors,
        "steps": steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the complete reversible PlanAnvil Git capability probe")
    add_source_argument(parser)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--temp-parent", type=Path)
    args = parser.parse_args()
    payload = probe_git_capabilities(args.source, args.run_id, args.temp_parent)
    return emit(payload, exit_code=0 if payload["ok"] else 2)


if __name__ == "__main__":
    cli_main(main)
