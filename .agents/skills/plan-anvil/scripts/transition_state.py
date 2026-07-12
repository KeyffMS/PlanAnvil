from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import (
    GENERATOR_STATES,
    PlanAnvilError,
    atomic_write_json,
    cli_main,
    emit,
    load_json,
    sha256_file,
    utc_now,
)
from schema_validator import assert_valid_file


ALLOWED = {
    "NEW": {"SOURCE_PREFLIGHT_PASSED"},
    "SOURCE_PREFLIGHT_PASSED": {"GIT_READY"},
    "GIT_READY": {"PLANNING_WORKTREE_READY"},
    "PLANNING_WORKTREE_READY": {"PROFILE_READY"},
    "PROFILE_READY": {"INSTRUCTION_MAP_READY"},
    "INSTRUCTION_MAP_READY": {"ANALYSIS_READY"},
    "ANALYSIS_READY": {"ARTIFACTS_GENERATED"},
    "ARTIFACTS_GENERATED": {"DETERMINISTICALLY_VALID"},
    "DETERMINISTICALLY_VALID": {"BLIND_REVIEW_WRITTEN"},
    "BLIND_REVIEW_WRITTEN": {"COMPARISON_VALID"},
    "COMPARISON_VALID": {"PLAN_COMMITTED"},
    "PLAN_COMMITTED": {"STOPPED"},
}


def transition_state(
    state_path: Path,
    *,
    expected_revision: int,
    new_status: str,
    phase: str | None,
    next_action_type: str,
    next_action_target: str | None,
    blocker: str | None = None,
    hash_paths: list[Path] | None = None,
) -> dict[str, Any]:
    state = load_json(state_path)
    if state.get("revision") != expected_revision:
        raise PlanAnvilError(
            f"Stale state revision: expected {expected_revision}, found {state.get('revision')}",
            code="STALE_STATE_REVISION",
        )
    current = state.get("status")
    allowed = ALLOWED.get(current, set())
    if new_status not in allowed and new_status not in {"BLOCKED", "FAILED"}:
        raise PlanAnvilError(f"Invalid transition {current} → {new_status}", code="INVALID_STATE_TRANSITION")
    if current in {"STOPPED", "BLOCKED", "FAILED"}:
        raise PlanAnvilError(f"Terminal state cannot transition: {current}", code="TERMINAL_STATE")

    blockers = list(state.get("open_blockers", []))
    if blocker and blocker not in blockers:
        blockers.append(blocker)
    artifact_hashes = dict(state.get("artifact_hashes", {}))
    for path in hash_paths or []:
        if not path.is_file():
            raise PlanAnvilError(f"Cannot hash missing artifact: {path}", code="MISSING_ARTIFACT")
        try:
            key = path.resolve().relative_to(state_path.parent.resolve()).as_posix()
        except ValueError:
            key = path.name
        artifact_hashes[key] = sha256_file(path)

    replacement = {
        **state,
        "revision": expected_revision + 1,
        "updated_at": utc_now(),
        "status": new_status,
        "current_phase": phase,
        "next_action": {"type": next_action_type, "target": next_action_target},
        "open_blockers": blockers,
        "artifact_hashes": artifact_hashes,
    }
    if new_status in {"STOPPED", "BLOCKED", "FAILED"} and next_action_type != "NONE":
        raise PlanAnvilError("Terminal state must use next_action.type = NONE", code="INVALID_TERMINAL_ACTION")
    atomic_write_json(state_path, replacement)
    schema = Path(__file__).resolve().parent.parent / "schemas/state.schema.json"
    assert_valid_file(state_path, schema)
    return replacement


def main() -> int:
    parser = argparse.ArgumentParser(description="Atomically advance PlanAnvil canonical state")
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--expected-revision", type=int, required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--phase")
    parser.add_argument("--next-action", required=True)
    parser.add_argument("--target")
    parser.add_argument("--blocker")
    parser.add_argument("--hash-path", type=Path, action="append", default=[])
    args = parser.parse_args()
    state = transition_state(
        args.state,
        expected_revision=args.expected_revision,
        new_status=args.status,
        phase=args.phase,
        next_action_type=args.next_action,
        next_action_target=args.target,
        blocker=args.blocker,
        hash_paths=args.hash_path,
    )
    return emit({"ok": True, "result": "STATE_UPDATED", "state": state})


if __name__ == "__main__":
    cli_main(main)
