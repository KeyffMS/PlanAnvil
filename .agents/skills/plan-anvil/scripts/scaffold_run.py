from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import (
    CONTRACT_VERSION,
    GENERATOR_VERSION,
    PLAN_ID_RE,
    RUN_ID_RE,
    SCHEMA_VERSION,
    PlanAnvilError,
    append_ignore_rules,
    atomic_write_json,
    atomic_write_text,
    canonical_json_text,
    cli_main,
    discover_repo,
    emit,
    git,
    is_ignored,
    is_tracked,
    load_json,
    repository_fingerprint,
    sha256_file,
    sha256_text,
    source_snapshot,
    utc_now,
)
from schema_validator import assert_valid_file


DIRECTORIES = [
    "stages",
    "checkpoints",
    "reports/validation",
    "reports/plan-review",
    "risks",
    "evidence",
    "diffs",
    "logs",
    "incidents",
    "final",
]


def _template(name: str) -> str:
    path = Path(__file__).resolve().parent.parent / "templates" / name
    return path.read_text(encoding="utf-8")


REQUIRED_GIT_STEPS = [
    "create_temporary_ref",
    "verify_temporary_ref",
    "delete_temporary_ref",
    "create_probe_branch",
    "create_probe_worktree",
    "checkout_probe_worktree",
    "create_probe_file",
    "update_probe_index",
    "create_probe_commit",
    "verify_probe_clean",
]


def _git_evidence(
    capability_report: dict[str, Any] | None,
    *,
    source_repo: Path,
    source_state: dict[str, Any],
    base_branch: str,
    base_sha: str,
    verified_at: str,
) -> dict[str, Any]:
    if not isinstance(capability_report, dict):
        raise PlanAnvilError("A complete Git capability report is required", code="CAPABILITY_REPORT_REQUIRED")
    if capability_report.get("ok") is not True or capability_report.get("result") != "GIT_READY":
        raise PlanAnvilError("Git capability report is not GIT_READY", code="GIT_NOT_READY")
    report_root = capability_report.get("repository_root")
    if not isinstance(report_root, str) or Path(report_root).resolve() != source_repo.resolve():
        raise PlanAnvilError("Git capability report belongs to a different repository", code="CAPABILITY_REPOSITORY_MISMATCH")
    report_snapshot = capability_report.get("source_snapshot")
    if not isinstance(report_snapshot, dict) or report_snapshot != source_state or report_snapshot.get("head") != base_sha:
        raise PlanAnvilError("Git capability evidence is stale", code="CAPABILITY_REPORT_STALE")
    if capability_report.get("base_branch") != base_branch:
        raise PlanAnvilError("Git capability base branch differs from the planning base", code="CAPABILITY_BASE_MISMATCH")
    if capability_report.get("source_snapshot_changed") not in ([], None):
        raise PlanAnvilError("Git capability probe changed the source worktree", code="CAPABILITY_SOURCE_CHANGED")
    cleanup_errors = capability_report.get("cleanup_errors")
    if cleanup_errors != []:
        raise PlanAnvilError("Git capability cleanup was not verified", code="CAPABILITY_CLEANUP_FAILED", details=cleanup_errors)
    steps = capability_report.get("steps")
    if not isinstance(steps, list):
        raise PlanAnvilError("Git capability steps are missing", code="CAPABILITY_REPORT_INCOMPLETE")
    step_results = {item.get("step"): item.get("ok") for item in steps if isinstance(item, dict)}
    missing = [step for step in REQUIRED_GIT_STEPS if step_results.get(step) is not True]
    if missing:
        raise PlanAnvilError("Git capability report did not pass every required operation", code="CAPABILITY_REPORT_INCOMPLETE", details=missing)
    return {
        "schema_version": SCHEMA_VERSION,
        "verified_at": verified_at,
        "result": "GIT_READY",
        "base_branch": base_branch,
        "base_sha": base_sha,
        "source_snapshot": source_state,
        "steps": [{"id": step, "result": "PASS"} for step in REQUIRED_GIT_STEPS],
        "cleanup": {"result": "PASS", "errors": []},
    }


def scaffold_run(
    planning: Path,
    source: Path,
    *,
    plan_id: str,
    run_id: str,
    slug: str,
    goal: str,
    base_branch: str,
    base_sha: str,
    capability_report: dict[str, Any] | None = None,
    codex_version: str = "unknown",
    model: str = "unknown",
    permission_mode: str = "unknown",
    project_trust: str = "UNKNOWN",
    hook_mode: str = "HOOKS_UNAVAILABLE",
) -> dict[str, Any]:
    if not PLAN_ID_RE.fullmatch(plan_id):
        raise PlanAnvilError(f"Invalid plan id: {plan_id}", code="INVALID_PLAN_ID")
    if not RUN_ID_RE.fullmatch(run_id):
        raise PlanAnvilError(f"Invalid run id: {run_id}", code="INVALID_RUN_ID")
    if not goal.strip():
        raise PlanAnvilError("Goal must not be empty", code="EMPTY_GOAL")
    if project_trust not in {"TRUSTED", "UNTRUSTED", "UNKNOWN"}:
        raise PlanAnvilError(f"Invalid project trust: {project_trust}", code="INVALID_RUNTIME_METADATA")
    if hook_mode not in {"HOOKS_TRUSTED", "HOOKS_DISABLED", "HOOKS_UNTRUSTED", "HOOKS_UNAVAILABLE"}:
        raise PlanAnvilError(f"Invalid hook mode: {hook_mode}", code="INVALID_RUNTIME_METADATA")

    repo = discover_repo(planning)
    source_repo = discover_repo(source)
    branch = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False).stdout.strip()
    expected_branch = f"pursue/plan/{plan_id}/{slug}"
    if branch != expected_branch:
        raise PlanAnvilError(
            f"Expected planning branch {expected_branch}, got {branch or 'detached HEAD'}",
            code="PLANNING_BRANCH_MISMATCH",
        )
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    if head != base_sha:
        raise PlanAnvilError("Planning worktree no longer points at the verified base SHA", code="BASE_SHA_MISMATCH")

    profile = repo / ".pursue/SYSTEM_PROFILE.md"
    local_profile = repo / ".pursue/SYSTEM_PROFILE.local.md"
    if not profile.is_file() or not local_profile.is_file():
        raise PlanAnvilError("Profiles must exist before scaffolding a run", code="PROFILE_MISSING")

    source_state = source_snapshot(source_repo)
    if source_state["head"] != base_sha:
        raise PlanAnvilError("Source HEAD differs from the verified base SHA", code="SOURCE_CHANGED")
    created_at = utc_now()
    git_evidence = _git_evidence(
        capability_report,
        source_repo=source_repo,
        source_state=source_state,
        base_branch=base_branch,
        base_sha=base_sha,
        verified_at=created_at,
    )

    run_rel = Path(".pursue/runs") / run_id
    run_root = repo / run_rel
    if run_root.exists():
        raise PlanAnvilError(f"Run already exists: {run_rel.as_posix()}", code="RUN_EXISTS")
    for directory in DIRECTORIES:
        (run_root / directory).mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "plan_id": plan_id,
        "run_id": run_id,
        "created_at": created_at,
        "generator_version": GENERATOR_VERSION,
        "repository": {
            "fingerprint": repository_fingerprint(repo),
            "base_branch": base_branch,
            "base_sha": base_sha,
            "planning_branch": branch,
        },
        "paths": {
            "run_root": run_rel.as_posix(),
            "plan": "PLAN.md",
            "state": "state.json",
            "compliance": "compliance.json",
            "traceability": "traceability.json",
            "repository_profile": ".pursue/SYSTEM_PROFILE.md",
            "local_state": "local-state.json",
        },
        "contract_versions": {
            "implementation_spec": CONTRACT_VERSION,
            "plan_contract": "1.0.0",
            "artifact_schema": SCHEMA_VERSION,
        },
    }
    state = {
        "schema_version": SCHEMA_VERSION,
        "revision": 4,
        "updated_at": created_at,
        "mode": "PLAN_GENERATION",
        "status": "PROFILE_READY",
        "current_stage": None,
        "current_phase": "DISCOVER_INSTRUCTIONS",
        "next_action": {"type": "MAP_INSTRUCTIONS", "target": "evidence/instruction-map.json"},
        "last_checkpoint": None,
        "open_blockers": [],
        "artifact_hashes": {},
    }
    compliance = {
        "schema_version": SCHEMA_VERSION,
        "verified_at": created_at,
        "codex": {
            "version": codex_version or "unknown",
            "model": model or "unknown",
            "permission_mode": permission_mode or "unknown",
            "project_trust": project_trust,
            "hook_mode": hook_mode,
        },
        "capabilities": [
            {"id": "CAP-SKILL-DISCOVERY", "status": "DOCUMENTED", "required": True, "evidence": []},
            {"id": "CAP-EXPLICIT-ACTIVATION", "status": "DOCUMENTED", "required": True, "evidence": []},
            {"id": "CAP-GIT-PROBE", "status": "VERIFIED", "required": True, "evidence": [(run_rel / "evidence/git-capability.json").as_posix()]},
            {"id": "CAP-INSTRUCTION-MAP", "status": "UNKNOWN", "required": True, "evidence": []},
            {"id": "CAP-BLIND-REVIEW", "status": "UNKNOWN", "required": True, "evidence": []},
        ],
        "unsupported": [
            "Generator execution of implementation stages",
            "Automatic base-branch push or merge",
            "Hooks as the sole enforcement boundary",
        ],
        "warnings": [
            warning
            for warning in [
                "Codex version is unknown." if not codex_version or codex_version == "unknown" else None,
                "Model slug is unknown." if not model or model == "unknown" else None,
                "Permission mode is unknown." if not permission_mode or permission_mode == "unknown" else None,
                "Project trust is unknown." if project_trust == "UNKNOWN" else None,
                "Hooks are not verified active; deterministic postconditions remain mandatory." if hook_mode != "HOOKS_TRUSTED" else None,
            ]
            if warning
        ],
    }
    traceability = {
        "schema_version": SCHEMA_VERSION,
        "requirements": [],
        "criteria": [],
        "controls": [],
        "gaps": [],
    }

    lifecycle = {
        "schema_version": SCHEMA_VERSION,
        "recorded_at": created_at,
        "events": [
            {"sequence": 1, "state": "SOURCE_PREFLIGHT_PASSED", "result": "PASS", "evidence": [(run_rel / "evidence/git-capability.json").as_posix()]},
            {"sequence": 2, "state": "GIT_READY", "result": "PASS", "evidence": [(run_rel / "evidence/git-capability.json").as_posix()]},
            {"sequence": 3, "state": "PLANNING_WORKTREE_READY", "result": "PASS", "evidence": [(run_rel / "manifest.json").as_posix()]},
            {"sequence": 4, "state": "PROFILE_READY", "result": "PASS", "evidence": [".pursue/SYSTEM_PROFILE.md"]},
        ],
    }
    state["artifact_hashes"] = {
        "evidence/git-capability.json": sha256_text(canonical_json_text(git_evidence)),
        "evidence/lifecycle.json": sha256_text(canonical_json_text(lifecycle)),
        ".pursue/SYSTEM_PROFILE.md": sha256_file(profile),
    }
    local_state = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "updated_at": created_at,
        "paths": {
            "source_worktree": str(source_repo.resolve()),
            "planning_worktree": str(repo.resolve()),
            "local_profile": str(local_profile.resolve()),
        },
        "hashes": {"local_profile": sha256_file(local_profile)},
        "source_snapshot": source_state,
    }

    atomic_write_json(run_root / "manifest.json", manifest)
    atomic_write_json(run_root / "evidence/git-capability.json", git_evidence)
    atomic_write_json(run_root / "evidence/lifecycle.json", lifecycle)
    atomic_write_json(run_root / "state.json", state)
    atomic_write_json(run_root / "compliance.json", compliance)
    atomic_write_json(run_root / "traceability.json", traceability)
    atomic_write_json(run_root / "local-state.json", local_state)
    atomic_write_text(run_root / "evidence/original-goal.md", "# Original goal\n\n" + goal.strip() + "\n")

    plan = _template("PLAN.md")
    replacements = {
        "{{TITLE}}": slug.replace("-", " ").title(),
        "{{PLAN_ID}}": plan_id,
        "{{RUN_ID}}": run_id,
        "{{BASE_BRANCH}}": base_branch,
        "{{BASE_SHA}}": base_sha,
        "{{PLANNING_BRANCH}}": branch,
        "{{GOAL}}": goal.strip(),
        "{{STATUS}}": "DRAFT",
        "{{NEXT_ACTION}}": "Complete repository analysis and author the plan.",
    }
    for key, value in replacements.items():
        plan = plan.replace(key, value)
    atomic_write_text(run_root / "PLAN.md", plan)

    append_ignore_rules(
        repo,
        [
            ".pursue/SYSTEM_PROFILE.local.md",
            ".pursue/runs/*/local-state.json",
            ".pursue/runs/*/.generation-lock",
            ".pursue/runs/*/.execution-lock",
        ],
    )
    if not is_ignored(repo, run_root / "local-state.json") or is_tracked(repo, run_root / "local-state.json"):
        raise PlanAnvilError("local-state.json is not safely ignored and untracked", code="LOCAL_STATE_NOT_IGNORED")

    schema_root = Path(__file__).resolve().parent.parent / "schemas"
    for filename in ["manifest", "state", "compliance", "traceability", "local-state"]:
        assert_valid_file(run_root / f"{filename}.json", schema_root / f"{filename}.schema.json")
    assert_valid_file(run_root / "evidence/git-capability.json", schema_root / "git-capability.schema.json")
    assert_valid_file(run_root / "evidence/lifecycle.json", schema_root / "lifecycle.schema.json")

    return {
        "ok": True,
        "result": "RUN_SCAFFOLDED",
        "run_root": run_rel.as_posix(),
        "plan": (run_rel / "PLAN.md").as_posix(),
        "state": state["status"],
        "next_action": state["next_action"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold a durable PlanAnvil run")
    parser.add_argument("--planning", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--plan-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--slug", required=True)
    goal_group = parser.add_mutually_exclusive_group(required=True)
    goal_group.add_argument("--goal")
    goal_group.add_argument("--goal-file", type=Path)
    parser.add_argument("--base-branch", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--capability-report", type=Path, required=True)
    parser.add_argument("--codex-version", default="unknown")
    parser.add_argument("--model", default="unknown")
    parser.add_argument("--permission-mode", default="unknown")
    parser.add_argument("--project-trust", choices=["TRUSTED", "UNTRUSTED", "UNKNOWN"], default="UNKNOWN")
    parser.add_argument(
        "--hook-mode",
        choices=["HOOKS_TRUSTED", "HOOKS_DISABLED", "HOOKS_UNTRUSTED", "HOOKS_UNAVAILABLE"],
        default="HOOKS_UNAVAILABLE",
    )
    args = parser.parse_args()
    goal = args.goal if args.goal is not None else args.goal_file.read_text(encoding="utf-8")
    payload = scaffold_run(
        args.planning,
        args.source,
        plan_id=args.plan_id,
        run_id=args.run_id,
        slug=args.slug,
        goal=goal,
        base_branch=args.base_branch,
        base_sha=args.base_sha,
        capability_report=load_json(args.capability_report),
        codex_version=args.codex_version,
        model=args.model,
        permission_mode=args.permission_mode,
        project_trust=args.project_trust,
        hook_mode=args.hook_mode,
    )
    return emit(payload)


if __name__ == "__main__":
    cli_main(main)
