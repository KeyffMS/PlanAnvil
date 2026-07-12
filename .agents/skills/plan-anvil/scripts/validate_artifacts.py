from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import (
    PlanAnvilError,
    atomic_write_json,
    canonical_file_is_valid,
    cli_main,
    discover_repo,
    emit,
    is_ignored,
    is_tracked,
    load_json,
    repo_relative,
    scan_privacy,
    sha256_file,
    utc_now,
)
from schema_validator import validate_file


SCHEMA_FILES = {
    "manifest.json": "manifest.schema.json",
    "state.json": "state.schema.json",
    "compliance.json": "compliance.schema.json",
    "traceability.json": "traceability.schema.json",
    "local-state.json": "local-state.schema.json",
    "evidence/git-capability.json": "git-capability.schema.json",
    "evidence/lifecycle.json": "lifecycle.schema.json",
}


def _resolve_run_root(repo: Path, run_root: Path) -> Path:
    candidate = run_root if run_root.is_absolute() else repo / run_root
    candidate = candidate.resolve()
    try:
        candidate.relative_to(repo)
    except ValueError as exc:
        raise PlanAnvilError("Run root escapes planning repository", code="PATH_ESCAPE") from exc
    return candidate


def validate_artifacts(planning: Path, run_root: Path, *, phase: str = "pre-review", write_report: bool = True) -> dict[str, Any]:
    repo = discover_repo(planning)
    run = _resolve_run_root(repo, run_root)
    schemas = Path(__file__).resolve().parent.parent / "schemas"
    findings: list[dict[str, Any]] = []
    validated: list[str] = []

    for filename, schema_name in SCHEMA_FILES.items():
        path = run / filename
        if not path.is_file():
            findings.append({"kind": "missing", "path": repo_relative(repo, path)})
            continue
        errors = validate_file(path, schemas / schema_name)
        if errors:
            findings.append({"kind": "schema", "path": repo_relative(repo, path), "errors": errors})
        elif not canonical_file_is_valid(path):
            findings.append({"kind": "non-canonical-json", "path": repo_relative(repo, path)})
        else:
            validated.append(repo_relative(repo, path))

    manifest = load_json(run / "manifest.json") if (run / "manifest.json").is_file() else {}
    state = load_json(run / "state.json") if (run / "state.json").is_file() else {}
    compliance = load_json(run / "compliance.json") if (run / "compliance.json").is_file() else {}
    traceability = load_json(run / "traceability.json") if (run / "traceability.json").is_file() else {}

    if manifest:
        if manifest.get("run_id") != run.name:
            findings.append({"kind": "run-id-mismatch", "expected": run.name, "actual": manifest.get("run_id")})
        expected_root = repo_relative(repo, run)
        if manifest.get("paths", {}).get("run_root") != expected_root:
            findings.append({"kind": "run-root-mismatch", "expected": expected_root, "actual": manifest.get("paths", {}).get("run_root")})

    git_evidence = load_json(run / "evidence/git-capability.json") if (run / "evidence/git-capability.json").is_file() else {}
    if git_evidence and manifest:
        if git_evidence.get("base_sha") != manifest.get("repository", {}).get("base_sha"):
            findings.append({"kind": "git-evidence-base-sha-mismatch"})
        if git_evidence.get("base_branch") != manifest.get("repository", {}).get("base_branch"):
            findings.append({"kind": "git-evidence-base-branch-mismatch"})
        required_steps = {
            "create_temporary_ref", "verify_temporary_ref", "delete_temporary_ref",
            "create_probe_branch", "create_probe_worktree", "checkout_probe_worktree",
            "create_probe_file", "update_probe_index", "create_probe_commit", "verify_probe_clean",
        }
        actual_steps = {item.get("id") for item in git_evidence.get("steps", []) if item.get("result") == "PASS"}
        if actual_steps != required_steps:
            findings.append({"kind": "git-evidence-step-mismatch", "missing": sorted(required_steps - actual_steps), "extra": sorted(actual_steps - required_steps)})

    lifecycle = load_json(run / "evidence/lifecycle.json") if (run / "evidence/lifecycle.json").is_file() else {}
    expected_bootstrap = ["SOURCE_PREFLIGHT_PASSED", "GIT_READY", "PLANNING_WORKTREE_READY", "PROFILE_READY"]
    if lifecycle:
        states = [item.get("state") for item in lifecycle.get("events", [])]
        sequences = [item.get("sequence") for item in lifecycle.get("events", [])]
        if states != expected_bootstrap or sequences != [1, 2, 3, 4]:
            findings.append({"kind": "bootstrap-lifecycle-order", "states": states, "sequences": sequences})
        for event in lifecycle.get("events", []):
            for relative in event.get("evidence", []):
                path = repo / relative
                try:
                    path.resolve().relative_to(repo.resolve())
                except ValueError:
                    findings.append({"kind": "lifecycle-evidence-path-escape", "path": relative})
                    continue
                if not path.is_file():
                    findings.append({"kind": "lifecycle-evidence-missing", "path": relative})

    local_state = run / "local-state.json"
    local_profile = repo / ".pursue/SYSTEM_PROFILE.local.md"
    for path in [local_state, local_profile]:
        if path.exists() and not is_ignored(repo, path):
            findings.append({"kind": "not-ignored", "path": repo_relative(repo, path)})
        if path.exists() and is_tracked(repo, path):
            findings.append({"kind": "tracked-local-state", "path": repo_relative(repo, path)})

    json_candidates = [
        path for path in run.rglob("*.json")
        if path.name != "local-state.json" and not any(part.startswith(".") for part in path.relative_to(run).parts)
    ]
    schema_by_location: list[tuple[Path, Path]] = []
    schema_by_location += [(path, schemas / "risk.schema.json") for path in (run / "risks").glob("RISK-*.json")]
    schema_by_location += [(path, schemas / "checkpoint.schema.json") for path in (run / "checkpoints").glob("CHECKPOINT-*.json")]
    analysis = run / "evidence/analysis.json"
    if analysis.exists():
        schema_by_location.append((analysis, schemas / "analysis.schema.json"))
    review_sidecar = run / "reports/plan-review/blind-review.json"
    comparison = run / "reports/plan-review/comparison.json"
    if review_sidecar.exists():
        schema_by_location.append((review_sidecar, schemas / "review.schema.json"))
    if comparison.exists():
        schema_by_location.append((comparison, schemas / "comparison.schema.json"))

    for path, schema in schema_by_location:
        errors = validate_file(path, schema)
        if errors:
            findings.append({"kind": "schema", "path": repo_relative(repo, path), "errors": errors})
        if not canonical_file_is_valid(path):
            findings.append({"kind": "non-canonical-json", "path": repo_relative(repo, path)})
        validated.append(repo_relative(repo, path))

    for path in json_candidates:
        if not canonical_file_is_valid(path):
            findings.append({"kind": "non-canonical-json", "path": repo_relative(repo, path)})

    committed_candidates = [
        repo / ".pursue/SYSTEM_PROFILE.md",
        *[
            path for path in run.rglob("*")
            if path.is_file() and path.name != "local-state.json" and not path.name.startswith(".")
        ],
    ]
    findings.extend(scan_privacy(repo, committed_candidates))

    referenced_risks = {
        risk_id
        for criterion in traceability.get("criteria", [])
        for risk_id in criterion.get("risks", [])
    }
    available_risks = {
        load_json(path).get("id")
        for path in (run / "risks").glob("RISK-*.json")
        if path.is_file()
    }
    for risk_id in sorted(referenced_risks - available_risks):
        findings.append({"kind": "missing-risk-file", "risk": risk_id})

    for capability in compliance.get("capabilities", []):
        if not capability.get("required"):
            continue
        status = capability.get("status")
        if status in {"FAILED", "BLOCKED"}:
            findings.append({"kind": "required-capability-failed", "capability": capability.get("id"), "status": status})
        if phase == "final" and status == "UNKNOWN":
            findings.append({"kind": "required-capability-unknown", "capability": capability.get("id")})

    if phase == "final":
        if not review_sidecar.is_file() or not (run / "reports/plan-review/blind-review.md").is_file():
            findings.append({"kind": "missing-blind-review"})
        if not comparison.is_file():
            findings.append({"kind": "missing-comparison"})
        elif load_json(comparison).get("result") != "PASS":
            findings.append({"kind": "comparison-not-pass"})

    for rel, expected_hash in state.get("artifact_hashes", {}).items():
        candidates = [run / rel, run / Path(rel).name, repo / rel]
        existing = next((path for path in candidates if path.is_file()), None)
        if existing is None:
            findings.append({"kind": "hashed-artifact-missing", "path": rel})
        elif sha256_file(existing) != expected_hash:
            findings.append({"kind": "hashed-artifact-stale", "path": rel})

    payload = {
        "schema_version": "1.1.0",
        "generated_at": utc_now(),
        "validator": "validate_artifacts",
        "phase": phase,
        "result": "PASS" if not findings else "FAIL",
        "findings": findings,
        "validated": sorted(set(validated)),
    }
    if write_report:
        atomic_write_json(run / "reports/validation/artifacts.json", payload)
    return {"ok": not findings, **payload}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate PlanAnvil canonical artifacts, schemas, privacy, and ignored local state")
    parser.add_argument("--planning", type=Path, default=Path.cwd())
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--phase", choices=["pre-review", "final"], default="pre-review")
    parser.add_argument("--no-write-report", action="store_true")
    args = parser.parse_args()
    payload = validate_artifacts(args.planning, args.run_root, phase=args.phase, write_report=not args.no_write_report)
    return emit(payload, exit_code=0 if payload["ok"] else 2)


if __name__ == "__main__":
    cli_main(main)
