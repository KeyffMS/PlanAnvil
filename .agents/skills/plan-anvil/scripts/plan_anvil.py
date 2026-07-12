from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import cli_main, emit, load_json, make_plan_id, make_run_id, slugify
from create_planning_worktree import create_planning_worktree
from preflight import preflight
from profile_repository import profile_repository
from scaffold_run import scaffold_run
from test_git_capabilities import probe_git_capabilities
from validate_all import validate_all


def start(
    source: Path,
    goal: str,
    destination: Path | None = None,
    *,
    codex_version: str = "unknown",
    model: str = "unknown",
    permission_mode: str = "unknown",
    project_trust: str = "UNKNOWN",
    hook_mode: str = "HOOKS_UNAVAILABLE",
) -> dict[str, Any]:
    goal = goal.strip()
    slug = slugify(goal)
    plan_id = make_plan_id()
    probe_run_id = make_run_id(plan_id, slug)

    source_check = preflight(source)
    if not source_check["ok"]:
        return source_check

    capability = probe_git_capabilities(source, probe_run_id)
    if not capability["ok"]:
        return capability

    worktree = create_planning_worktree(
        source,
        plan_id=plan_id,
        slug=slug,
        capability_report=capability,
        destination=destination,
    )
    planning = Path(worktree["planning_worktree"])
    profile = profile_repository(planning, source)
    scaffold = scaffold_run(
        planning,
        source,
        plan_id=plan_id,
        run_id=worktree["run_id"],
        slug=slug,
        goal=goal,
        base_branch=worktree["base_branch"],
        base_sha=worktree["base_sha"],
        capability_report=capability,
        codex_version=codex_version,
        model=model,
        permission_mode=permission_mode,
        project_trust=project_trust,
        hook_mode=hook_mode,
    )
    return {
        "ok": True,
        "result": "PROFILE_READY",
        "plan_id": plan_id,
        "run_id": worktree["run_id"],
        "planning_branch": worktree["planning_branch"],
        "planning_worktree": worktree["planning_worktree"],
        "run_root": scaffold["run_root"],
        "plan": scaffold["plan"],
        "next_action": {
            "type": "MAP_INSTRUCTIONS",
            "instruction": "Determine affected paths, run map_instructions.py for all of them, then analyze the goal and replace every plan placeholder.",
        },
        "implementation_executed": False,
    }


def status(planning: Path, run_root: Path) -> dict[str, Any]:
    run = run_root if run_root.is_absolute() else planning / run_root
    return {
        "ok": True,
        "manifest": load_json(run / "manifest.json"),
        "state": load_json(run / "state.json"),
        "compliance": load_json(run / "compliance.json"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="PlanAnvil deterministic controller")
    sub = parser.add_subparsers(dest="command", required=True)

    start_parser = sub.add_parser("start", help="Preflight, probe Git, isolate planning worktree, profile, and scaffold")
    start_parser.add_argument("--source", type=Path, default=Path.cwd())
    start_goal = start_parser.add_mutually_exclusive_group(required=True)
    start_goal.add_argument("--goal")
    start_goal.add_argument("--goal-file", type=Path)
    start_parser.add_argument("--destination", type=Path)
    start_parser.add_argument("--codex-version", default="unknown")
    start_parser.add_argument("--model", default="unknown")
    start_parser.add_argument("--permission-mode", default="unknown")
    start_parser.add_argument("--project-trust", choices=["TRUSTED", "UNTRUSTED", "UNKNOWN"], default="UNKNOWN")
    start_parser.add_argument(
        "--hook-mode",
        choices=["HOOKS_TRUSTED", "HOOKS_DISABLED", "HOOKS_UNTRUSTED", "HOOKS_UNAVAILABLE"],
        default="HOOKS_UNAVAILABLE",
    )

    validate_parser = sub.add_parser("validate", help="Run deterministic validation")
    validate_parser.add_argument("--planning", type=Path, default=Path.cwd())
    validate_parser.add_argument("--run-root", type=Path, required=True)
    validate_parser.add_argument("--source", type=Path)
    validate_parser.add_argument("--phase", choices=["pre-review", "final"], default="pre-review")
    validate_parser.add_argument("--no-advance-state", action="store_true")

    status_parser = sub.add_parser("status", help="Read canonical run status")
    status_parser.add_argument("--planning", type=Path, default=Path.cwd())
    status_parser.add_argument("--run-root", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "start":
        goal = args.goal if args.goal is not None else args.goal_file.read_text(encoding="utf-8")
        payload = start(
            args.source,
            goal,
            args.destination,
            codex_version=args.codex_version,
            model=args.model,
            permission_mode=args.permission_mode,
            project_trust=args.project_trust,
            hook_mode=args.hook_mode,
        )
        return emit(payload, exit_code=0 if payload.get("ok") else 2)
    if args.command == "validate":
        payload = validate_all(
            args.planning,
            args.run_root,
            source=args.source,
            phase=args.phase,
            advance_state=not args.no_advance_state,
        )
        return emit(payload, exit_code=0 if payload.get("ok") else 2)
    return emit(status(args.planning, args.run_root))


if __name__ == "__main__":
    cli_main(main)
