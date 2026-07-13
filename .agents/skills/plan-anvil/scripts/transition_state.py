from __future__ import annotations

import argparse
import json
import os
import socket
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from common import (
    SCHEMA_VERSION,
    PlanAnvilError,
    atomic_write_json,
    atomic_write_text,
    canonical_json_text,
    cli_main,
    discover_repo,
    emit,
    load_json,
    sha256_file,
    sha256_text,
    utc_now,
)
from path_safety import assert_safe_run_root
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


def _owner_alive(owner: dict[str, Any]) -> bool | None:
    """Return True/False for a local owner and None when liveness is unverifiable."""
    pid = owner.get("pid")
    hostname_hash = owner.get("hostname_hash")
    if hostname_hash != sha256_text(socket.gethostname()):
        return None
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _write_lock(path: Path, payload: dict[str, Any], *, exclusive: bool = False) -> None:
    flags = os.O_WRONLY | os.O_CREAT
    flags |= os.O_EXCL if exclusive else os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _release_owned_lock(lock_path: Path, lock_id: str) -> None:
    try:
        current = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if isinstance(current, dict) and current.get("lock_id") == lock_id:
        lock_path.unlink(missing_ok=True)


@contextmanager
def run_lock(
    state_path: Path,
    *,
    command: str = "plan-anvil",
    stale_after_seconds: int = 300,
    heartbeat_interval_seconds: float = 30.0,
) -> Iterator[Path]:
    """Lock a complete PlanAnvil run operation with a durable heartbeat."""
    lock_path = state_path.parent / ".generation-lock"
    lock_id = sha256_text(
        f"{socket.gethostname()}:{os.getpid()}:{time.time_ns()}:{command}"
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": state_path.parent.name,
        "lock_id": lock_id,
        "owner": {
            "hostname_hash": sha256_text(socket.gethostname()),
            "pid": os.getpid(),
            "session_id_hash": sha256_text(os.environ.get("CODEX_SESSION_ID", "unknown")),
        },
        "created_at": utc_now(),
        "heartbeat_at": utc_now(),
        "command": command,
    }

    while True:
        try:
            _write_lock(lock_path, payload, exclusive=True)
        except FileExistsError:
            try:
                existing = json.loads(lock_path.read_text(encoding="utf-8"))
                age = time.time() - lock_path.stat().st_mtime
            except (OSError, json.JSONDecodeError) as exc:
                raise PlanAnvilError(
                    f"Generation lock exists but cannot be verified: {lock_path}",
                    code="GENERATION_LOCK_UNVERIFIABLE",
                ) from exc
            if age <= stale_after_seconds:
                raise PlanAnvilError(
                    f"Generation lock is active: {lock_path}",
                    code="GENERATION_LOCK_ACTIVE",
                    details=existing,
                )
            owner_alive = _owner_alive(existing.get("owner", {}))
            if owner_alive is None:
                raise PlanAnvilError(
                    f"Stale generation lock belongs to another host: {lock_path}",
                    code="GENERATION_LOCK_UNVERIFIABLE",
                    details=existing,
                )
            if owner_alive:
                raise PlanAnvilError(
                    f"Generation lock owner is still active: {lock_path}",
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
            break

    heartbeat_stop = threading.Event()
    heartbeat_errors: list[str] = []
    interval = max(1.0, min(heartbeat_interval_seconds, stale_after_seconds / 3))

    def heartbeat() -> None:
        while not heartbeat_stop.wait(interval):
            try:
                current = json.loads(lock_path.read_text(encoding="utf-8"))
                if current.get("lock_id") != lock_id:
                    heartbeat_errors.append("Run lock ownership changed during the operation.")
                    return
                current["heartbeat_at"] = utc_now()
                _write_lock(lock_path, current)
            except (OSError, json.JSONDecodeError) as exc:
                heartbeat_errors.append(str(exc))
                return

    heartbeat_thread = threading.Thread(
        target=heartbeat,
        name=f"plananvil-lock-{os.getpid()}",
        daemon=True,
    )
    heartbeat_thread.start()

    try:
        yield lock_path
    except BaseException:
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=max(2.0, interval + 1.0))
        _release_owned_lock(lock_path, lock_id)
        raise
    else:
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=max(2.0, interval + 1.0))
        _release_owned_lock(lock_path, lock_id)
        if heartbeat_errors:
            raise PlanAnvilError(
                "Run lock heartbeat failed",
                code="GENERATION_LOCK_HEARTBEAT_FAILED",
                details=heartbeat_errors,
            )


@contextmanager
def generation_lock(state_path: Path, *, stale_after_seconds: int = 300) -> Iterator[Path]:
    """Backward-compatible state-transition lock wrapper."""
    with run_lock(
        state_path,
        command="transition-state",
        stale_after_seconds=stale_after_seconds,
    ) as lock_path:
        yield lock_path


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
        atomic_write_text(state_path, original_text)
        assert_valid_file(state_path, schema_path)
        if isinstance(exc, PlanAnvilError):
            raise
        raise PlanAnvilError("State publication failed and was rolled back", code="STATE_PUBLICATION_FAILED") from exc


def _transition_state_unlocked(
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
            try:
                repo = discover_repo(state_path.parent)
                key = path.resolve().relative_to(repo).as_posix()
            except (PlanAnvilError, ValueError):
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
    lock_held: bool = False,
) -> dict[str, Any]:
    if lock_held:
        return _transition_state_unlocked(
            state_path,
            expected_revision=expected_revision,
            new_status=new_status,
            phase=phase,
            next_action_type=next_action_type,
            next_action_target=next_action_target,
            blocker=blocker,
            hash_paths=hash_paths,
        )
    with run_lock(state_path, command="transition-state"):
        return _transition_state_unlocked(
            state_path,
            expected_revision=expected_revision,
            new_status=new_status,
            phase=phase,
            next_action_type=next_action_type,
            next_action_target=next_action_target,
            blocker=blocker,
            hash_paths=hash_paths,
        )


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

    repo = discover_repo(args.state.parent)
    run = assert_safe_run_root(repo, args.state.parent)
    state_path = args.state.resolve()
    if state_path != (run / "state.json").resolve():
        raise PlanAnvilError(
            "Transition CLI requires the canonical <run-root>/state.json path",
            code="INVALID_STATE_PATH",
        )
    state = transition_state(
        state_path,
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
