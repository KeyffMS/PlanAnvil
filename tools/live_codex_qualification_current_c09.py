from __future__ import annotations

from pathlib import Path
from typing import Any

import live_codex_qualification as base
import live_codex_qualification_harness_v2 as v2
import live_codex_qualification_harness_v4 as v4
from live_codex_qualification_current_common import finish, runtime_paths
from live_codex_qualification_current_stateful import cleanup, isolated_home, segment_prompt, status_prompt, turn

LIMIT = 200


def run(
    *, root: Path, runtime_root: Path, schemas: dict[str, Path], version: str,
    os_name: str, source_commit: str, date: str,
) -> tuple[str, bool]:
    capability_id = "C09"
    _, cap_runtime, _, repo, worktrees, results, _ = runtime_paths(root, runtime_root, capability_id)
    with v2._python_bytecode_disabled():
        base.ensure_git_repo(repo)
        planning, _ = v4._start_active_run(
            root=root, repo=repo, worktrees=worktrees, version=version,
            compact_limit=LIMIT, create_checkpoint=True, segments=4, segment_bytes=65536,
        )
        fixture_commit = base.git(repo, "rev-parse", "HEAD")
        checkpoint_before = v4._checkpoint_validation(planning)
        v4._clear_hook_log(planning)
        home, auth, auth_before = isolated_home(cap_runtime, "c09-home")
        if auth is None:
            cleanup(home, auth, auth_before)
            return finish(
                root=root, cap_runtime=cap_runtime, capability_id=capability_id, result="BLOCKED",
                observations=["file_backed_auth_bridge_available=false"],
                blocker="C09 requires disposable persisted state with verifiable file-backed auth cleanup.",
                summary="C09 stateful transport preflight failed.", trials=[], fixture_commit=fixture_commit,
                version=version, os_name=os_name, source_commit=source_commit, date=date,
            )

        thread: str | None = None
        turns: list[dict[str, Any]] = []
        turn_error: str | None = None
        continued = False
        pre: list[dict[str, Any]] = []
        post: list[dict[str, Any]] = []
        checkpoint_after: dict[str, Any] = {"ok": False}
        try:
            for number in range(1, 5):
                payload, events, error, observed = turn(
                    cwd=planning, schemas=schemas, results=results, position=number,
                    home=home, limit=LIMIT, prompt=segment_prompt(capability_id, number), thread=thread,
                )
                thread = thread or observed
                turn_error = error or turn_error
                turns.append({"phase":f"pressure_turn_{number}","model_payload":payload,"event_summary":events,"error":error})
                records = v4._read_hook_records(planning)
                pre = v4._event_records(records, "PreCompact")
                post = v4._event_records(records, "PostCompact")
                if len(pre) >= 2 and len(post) >= 2:
                    break
                if thread is None:
                    break

            if thread is not None and len(pre) >= 2 and len(post) >= 2:
                payload, events, error, _ = turn(
                    cwd=planning, schemas=schemas, results=results, position=5,
                    home=home, limit=LIMIT, prompt=status_prompt(capability_id), thread=thread,
                )
                turn_error = error or turn_error
                continued = error is None and int(events.get("completed_command_items") or 0) >= 2
                turns.append({"phase":"after_second_compaction","model_payload":payload,"event_summary":events,"error":error})
            checkpoint_after = v4._checkpoint_validation(planning)
        finally:
            rollouts, clean, auth_ok = cleanup(home, auth, auth_before)

    repeated = len(pre) >= 2 and len(post) >= 2
    checkpoints = bool(checkpoint_before.get("ok")) and bool(checkpoint_after.get("ok"))
    if thread is None:
        result, blocker = "BLOCKED", "C09 first persisted turn emitted no exact resumable thread id."
    elif not repeated:
        result, blocker = "BLOCKED", turn_error or "C09 did not reach two real PreCompact/PostCompact cycles in the bounded exact-ID session."
    elif not checkpoints:
        result, blocker = "FAILED", "C09 checkpoint validation was not coherent before and after repeated compaction."
    elif not continued:
        result, blocker = "FAILED", "C09 did not demonstrate normal tool use after the second completed compaction."
    elif not (rollouts > 0 and clean and auth_ok):
        result, blocker = "BLOCKED", "C09 persisted-session cleanup/auth invariants failed."
    else:
        result, blocker = "REPRODUCED", None

    return finish(
        root=root, cap_runtime=cap_runtime, capability_id=capability_id, result=result,
        observations=[
            f"exact_thread_id_used={str(thread is not None).lower()}", f"precompact_count={len(pre)}", f"postcompact_count={len(post)}",
            f"checkpoint_before_valid={str(bool(checkpoint_before.get('ok'))).lower()}",
            f"checkpoint_after_valid={str(bool(checkpoint_after.get('ok'))).lower()}",
            f"continued_after_second_compaction={str(continued).lower()}",
            f"session_rollouts_created={rollouts}", f"session_cleanup_verified={str(clean).lower()}",
            f"auth_metadata_unchanged={str(auth_ok).lower()}",
        ],
        blocker=blocker,
        summary="C09 uses one exact-ID disposable persisted session to prove repeated compaction and continuation.",
        trials=turns, fixture_commit=fixture_commit, version=version, os_name=os_name,
        source_commit=source_commit, date=date,
    )
