from __future__ import annotations

import argparse
import json
import os
import socket
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from common import (
    GENERATOR_STATES,
    SCHEMA_VERSION,
    PlanAnvilError,
    atomic_write_json,
    atomic_write_text,
    canonical_json_text,
    cli_main,
    emit,
    load_json,
    sha256_file,
    sha256_text,
    utc_now,
)
from schema_validator import assert_valid_file, validate


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


def _owner_alive(owner: dict[str, Any]) -> bool:
    pid = owner.get("pid")
    hostname_hash = owner.get("hostname_hash")
    if not isinstance(pid, int) or pid <= 0:
        return False
    if hostname_hash != sha256_text(socket.gethostname()):
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@contextmanager
def generation_lock(state_path: Path, *, stale_after_seconds: int = 300) -> Iterator[Path]:
    lock_path = state_path.parent / ".generation-lock"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": state_path.parent.name,
        "owner": {
            "hostname_hash": sha256_text(socket.gethostname()),
            "pid": os.getpid(),
            "session_id_hash": sha256_text(os.environ.get("CODEX_SESSION_ID", "unknown")),
        },
        "created_at": utc_now(),
        "heartbeat_at": utc_now(),
        "command": "transition-state",
    }

    while True:
        try:
            fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            try:
                existing = json.loads(lock_path.read_text(encoding="utf-8"))
                age = time.time() - lock_path.stat().st_mtime
            except (OSError, json.JSONDecodeError) as exc:
                raise PlanAnvilError(
                    f"Generation lock exists but cannot be verified: {lock_path}",
                    code="GENERATION_LOCK_UNVERIFIABLE",
                ) from exc
            if age <= stale_after_seconds or _owner_alive(existing.get("owner", {})):
                raise PlanAnvilError(
                    f"Generation lock is active: {lock_path}",
                    code="GENERATION_LOCK_ACTIVE",
                    details=existing,
                )
            try:
                lock_path.unlink()
            except OSError as exc:
                raise PlanAnvilError(
                    f"Stale generation lock could not be removed: {lock_path}",
                    code="GENERATION_LOCK_STALE",
                ) from exc
            continue
        else:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            break

    try:
        yield lock_path
    finally:
        try:
            current = json.loads(lock_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            current = None
        if current == payload:
            lock_path.unlink(missing_ok=True)


def _validated_replace(state_path: Path, replacement: dict[str, Any], schema_path: Path) -> None:
    schema = load_json(schema_path)
    errors = validate(replacement, schema)
    if errors:
        raise PlanAnvilError(
            "Replacement state failed schema validation before publication",
            code="SCHEMA_VALIDATION_FAILED",
            details=errors,
        )

    original_text = state_path.read_text(encoding="utf-8")
    atomic_write_json(state_path, replacement)
    try:
        assert_valid_file(state_path, schema_path)
        if state_path.read_text(encoding="utf-8") != canonical_json_text(replacement):
            raise PlanAnvilError("State reread differs from published replacement", code="STATE_REREAD_MISMATCH")
    except Exception as exc:
        # Restore the last known-valid state so a failed postcondition does not
        # leave corrupt canonical state behind.
        atomic_write_text(state_path, original_text)
        assert_valid_file(state_path, schema_path)
        if isinstance(exc, PlanAnvilError):
            raise
        raise PlanAnvilError("State publication failed and was rolled back", code="STATE_PUBLICATION_FAILED") from exc


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
    with generation_lock(state_path):
        schema = Path(__file__).resolve().parent.parent / "schemas/state.schema.json"
        assert_valid_file(state_path, schema)
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
        _validated_replace(state_path, replacement, schema)
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
