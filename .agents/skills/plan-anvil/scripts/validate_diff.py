from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from artifact_policy import allowed_planning_path, allowed_run_artifacts
from common import (
    atomic_write_json,
    cli_main,
    compare_snapshot,
    discover_repo,
    emit,
    git,
    git_worktree_paths,
    list_untracked,
    load_json,
    repo_relative,
    repository_fingerprint,
    scan_privacy,
    utc_now,
)
from path_safety import assert_safe_repo_path, assert_safe_run_root
from schema_validator import assert_valid_file


def _changed_paths(repo: Path, base_sha: str) -> list[str]:
    result = git(repo, "diff", "--name-only", "-z", base_sha, "--")
    paths = [item for item in result.stdout.split("\0") if item]
    paths.extend(list_untracked(repo))
    return sorted(set(paths))


def _common_git_dir(repo: Path) -> Path:
    raw = Path(git(repo, "rev-parse", "--git-common-dir").stdout.strip())
    return raw.resolve() if raw.is_absolute() else (repo / raw).resolve()


def _source_identity_findings(
    planning_repo: Path,
    source_repo: Path,
    manifest: dict[str, Any],
    local_state: dict[str, Any],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    expected_fingerprint = manifest.get("repository", {}).get("fingerprint")
    actual_fingerprint = repository_fingerprint(source_repo)
    if actual_fingerprint != expected_fingerprint:
        findings.append({"kind": "source-repository-fingerprint-mismatch"})

    if _common_git_dir(source_repo) != _common_git_dir(planning_repo):
        findings.append({"kind": "source-git-common-dir-mismatch"})

    worktrees = set(git_worktree_paths(planning_repo))
    if source_repo.resolve() not in worktrees or planning_repo.resolve() not in worktrees:
        findings.append({"kind": "source-worktree-registration-mismatch"})

    snapshot = local_state.get("source_snapshot", {})
    base_sha = manifest.get("repository", {}).get("base_sha")
    base_branch = manifest.get("repository", {}).get("base_branch")
    if snapshot.get("head") != base_sha:
        findings.append({"kind": "source-snapshot-base-sha-mismatch"})
    if snapshot.get("branch") != base_branch:
        findings.append({"kind": "source-snapshot-base-branch-mismatch"})
    return findings


def validate_diff(
    planning: Path,
    run_root: Path,
    *,
    source: Path | None = None,
    extra_allowed: list[str] | None = None,
    write_report: bool = True,
) -> dict[str, Any]:
    repo = discover_repo(planning)
    run = assert_safe_run_root(repo, run_root)
    manifest = load_json(run / "manifest.json")
    local_state = load_json(run / "local-state.json")
    base_sha = manifest["repository"]["base_sha"]
    run_rel = repo_relative(repo, run)

    findings: list[dict[str, Any]] = []
    changed = _changed_paths(repo, base_sha)
    committed_candidates: list[Path] = []
    extra = set(extra_allowed or [])

    for rel in changed:
        if rel not in extra and not allowed_planning_path(rel, run_rel):
            findings.append({"kind": "path-outside-planning-artifact-policy", "path": rel})
            continue

        try:
            path = assert_safe_repo_path(repo, Path(rel))
        except Exception as exc:
            findings.append({"kind": getattr(exc, "code", "unsafe-path"), "path": rel})
            continue
        if path.is_symlink():
            try:
                path.resolve().relative_to(repo)
            except ValueError:
                findings.append({"kind": "symlink-escape", "path": rel})
                continue
        if path.is_file():
            committed_candidates.append(path)

    source_repo = (
        discover_repo(source)
        if source
        else discover_repo(Path(local_state["paths"]["source_worktree"]))
    )
    findings.extend(_source_identity_findings(repo, source_repo, manifest, local_state))
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
        "allowed": allowed_run_artifacts(run_rel),
        "changed_paths": changed,
        "findings": findings,
    }
    if write_report:
        target = run / "reports/validation/diff.json"
        atomic_write_json(target, payload)
        schema = Path(__file__).resolve().parent.parent / "schemas/validation-report.schema.json"
        assert_valid_file(target, schema)
    return {"ok": not findings, **payload}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate PlanAnvil planning-branch ownership and source immutability"
    )
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
