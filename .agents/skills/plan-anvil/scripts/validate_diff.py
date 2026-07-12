from __future__ import annotations

import argparse
import fnmatch
from pathlib import Path
from typing import Any

from common import (
    PlanAnvilError,
    atomic_write_json,
    cli_main,
    compare_snapshot,
    discover_repo,
    emit,
    ensure_inside,
    git,
    list_untracked,
    load_json,
    repo_relative,
    scan_privacy,
    utc_now,
)


def _changed_paths(repo: Path, base_sha: str) -> list[str]:
    result = git(repo, "diff", "--name-only", "-z", base_sha, "--")
    paths = [item for item in result.stdout.split("\0") if item]
    paths.extend(list_untracked(repo))
    return sorted(set(paths))


def _matches(path: str, allowed: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in allowed)


def validate_diff(
    planning: Path,
    run_root: Path,
    *,
    source: Path | None = None,
    extra_allowed: list[str] | None = None,
    write_report: bool = True,
) -> dict[str, Any]:
    repo = discover_repo(planning)
    run = (run_root if run_root.is_absolute() else repo / run_root).resolve()
    manifest = load_json(run / "manifest.json")
    local_state = load_json(run / "local-state.json")
    base_sha = manifest["repository"]["base_sha"]
    run_rel = repo_relative(repo, run)

    allowed = [
        ".gitignore",
        ".pursue/SYSTEM_PROFILE.md",
        f"{run_rel}/**",
    ]
    allowed.extend(extra_allowed or [])
    forbidden = [
        ".pursue/SYSTEM_PROFILE.local.md",
        f"{run_rel}/local-state.json",
        f"{run_rel}/.generation-lock",
        f"{run_rel}/.execution-lock",
    ]

    findings: list[dict[str, Any]] = []
    changed = _changed_paths(repo, base_sha)
    committed_candidates: list[Path] = []

    for rel in changed:
        if rel in forbidden or _matches(rel, forbidden):
            findings.append({"kind": "forbidden-local-artifact", "path": rel})
            continue
        if not _matches(rel, allowed):
            findings.append({"kind": "path-outside-planning-allowlist", "path": rel})
            continue
        path = repo / rel
        ensure_inside(repo, path)
        if path.is_symlink():
            try:
                path.resolve().relative_to(repo)
            except ValueError:
                findings.append({"kind": "symlink-escape", "path": rel})
        if path.is_file():
            committed_candidates.append(path)

    source_repo = discover_repo(source) if source else Path(local_state["paths"]["source_worktree"])
    changed_snapshot = compare_snapshot(source_repo, local_state["source_snapshot"])
    if changed_snapshot:
        findings.append({"kind": "source-worktree-changed", "fields": changed_snapshot})

    findings.extend(scan_privacy(repo, committed_candidates))

    payload = {
        "schema_version": "1.1.0",
        "generated_at": utc_now(),
        "validator": "validate_diff",
        "result": "PASS" if not findings else "FAIL",
        "base_sha": base_sha,
        "allowed": allowed,
        "changed_paths": changed,
        "findings": findings,
    }
    if write_report:
        atomic_write_json(run / "reports/validation/diff.json", payload)
    return {"ok": not findings, **payload}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate PlanAnvil planning-branch ownership and source immutability")
    parser.add_argument("--planning", type=Path, default=Path.cwd())
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--allow", action="append", default=[])
    parser.add_argument("--no-write-report", action="store_true")
    args = parser.parse_args()
    payload = validate_diff(
        args.planning,
        args.run_root,
        source=args.source,
        extra_allowed=args.allow,
        write_report=not args.no_write_report,
    )
    return emit(payload, exit_code=0 if payload["ok"] else 2)


if __name__ == "__main__":
    cli_main(main)
