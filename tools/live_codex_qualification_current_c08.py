from __future__ import annotations

from pathlib import Path
from typing import Any

import live_codex_qualification as base
import live_codex_qualification_harness_v2 as v2
import live_codex_qualification_harness_v4 as v4
from live_codex_qualification_current_common import finish, runtime_paths
from live_codex_qualification_current_stateful import cleanup, isolated_home, recovery_stops, segment_prompt, status_prompt, turn

LIMIT = 200


def run(
    *, root: Path, runtime_root: Path, schemas: dict[str, Path], version: str,
    os_name: str, source_commit: str, date: str,
) -> tuple[str, bool]:
    capability_id = "C08"
    _, cap_runtime, _, repo, worktrees, results, _ = runtime_paths(root, runtime_root, capability_id)
    with v2._python_bytecode_disabled():
        base.ensure_git_repo(repo)
        planning, run_root = v4._start_active_run(
            root=root, repo=repo, worktrees=worktrees, version=version,
            compact_limit=LIMIT, create_checkpoint=False, segments=3, segment_bytes=65536,
        )
        fixture_commit = base.git(repo, "rev-parse", "HEAD")
        invalid_checkpoint = v4._checkpoint_validation(planning)
        v4._clear_hook_log(planning)
        home, auth, auth_before = isolated_home(cap_runtime, "c08-home")
        if auth is None:
            cleanup(home, auth, auth_before)
            return finish(
                root=root, cap_runtime=cap_runtime, capability_id=capability_id, result="BLOCKED",
                observations=["file_backed_auth_bridge_available=false"],
                blocker="C08 requires disposable persisted state with verifiable file-backed auth cleanup.",
                summary="C08 stateful transport preflight failed.", trials=[], fixture_commit=fixture_commit,
                version=version, os_name=os_name, source_commit=source_commit, date=date,
            )

        thread: str | None = None
        turns: list[dict[str, Any]] = []
        invalid_ok = False
        repaired_ok = False
        repair_error: str | None = None
        repaired_checkpoint: dict[str, Any] = {"ok": False}
        pre_bad: list[dict[str, Any]] = []
        post_bad: list[dict[str, Any]] = []
        stop_bad: list[dict[str, Any]] = []
        pre_good: list[dict[str, Any]] = []
        post_good: list[dict[str, Any]] = []
        err1: str | None = None
        err2: str | None = None
        try:
            payload1, events1, err1, thread = turn(
                cwd=planning, schemas=schemas, results=results, position=1,
                home=home, limit=LIMIT, prompt=segment_prompt(capability_id, 1), thread=None,
            )
            if thread is not None:
                payload2, events2, err2, _ = turn(
                    cwd=planning, schemas=schemas, results=results, position=2,
                    home=home, limit=LIMIT, prompt=status_prompt(capability_id), thread=thread,
                )
            else:
                payload2, events2, err2 = {}, {}, "first turn emitted no exact thread id"
            turns.extend([
                {"phase":"invalid_pressure","model_payload":payload1,"event_summary":events1,"error":err1},
                {"phase":"invalid_next_user_turn","model_payload":payload2,"event_summary":events2,"error":err2},
            ])
            invalid_records = v4._read_hook_records(planning)
            pre_bad = v4._event_records(invalid_records, "PreCompact")
            post_bad = v4._event_records(invalid_records, "PostCompact")
            stop_bad = recovery_stops(invalid_records)
            invalid_ok = not bool(invalid_checkpoint.get("ok")) and bool(pre_bad) and bool(stop_bad) and not post_bad

            if invalid_ok and thread is not None:
                v4._create_checkpoint(planning=planning, run_root=run_root)
                repaired_checkpoint = v4._checkpoint_validation(planning)
                v4._clear_hook_log(planning)
                payload3, events3, repair_error, _ = turn(
                    cwd=planning, schemas=schemas, results=results, position=3,
                    home=home, limit=LIMIT, prompt=segment_prompt(capability_id, 2), thread=thread,
                )
                records = v4._read_hook_records(planning)
                pre_good = v4._event_records(records, "PreCompact")
                post_good = v4._event_records(records, "PostCompact")
                repaired_ok = bool(repaired_checkpoint.get("ok")) and bool(pre_good) and bool(post_good) and not recovery_stops(records)
                turns.append({"phase":"repaired_checkpoint","model_payload":payload3,"event_summary":events3,"error":repair_error})
        finally:
            rollouts, clean, auth_ok = cleanup(home, auth, auth_before)

    if not invalid_ok:
        result, blocker = "BLOCKED", err1 or err2 or "No real recovery-blocking PreCompact was observed at the audited next-user-turn trigger boundary."
    elif not repaired_ok:
        result, blocker = (("BLOCKED", repair_error) if repair_error else ("FAILED", "Checkpoint repair did not produce an allowed PreCompact/PostCompact cycle."))
    elif not (rollouts > 0 and clean and auth_ok):
        result, blocker = "BLOCKED", "C08 persisted-session cleanup/auth invariants failed."
    else:
        result, blocker = "REPRODUCED", None

    return finish(
        root=root, cap_runtime=cap_runtime, capability_id=capability_id, result=result,
        observations=[
            f"exact_thread_id_used={str(thread is not None).lower()}",
            f"invalid_precompact_count={len(pre_bad)}", f"invalid_postcompact_count={len(post_bad)}",
            f"invalid_recovery_stop_count={len(stop_bad)}",
            f"repaired_checkpoint_valid={str(bool(repaired_checkpoint.get('ok'))).lower()}",
            f"repaired_precompact_count={len(pre_good)}", f"repaired_postcompact_count={len(post_good)}",
            f"session_rollouts_created={rollouts}", f"session_cleanup_verified={str(clean).lower()}",
            f"auth_metadata_unchanged={str(auth_ok).lower()}",
        ],
        blocker=blocker,
        summary="C08 qualifies the real next-user-turn compaction lifecycle in one exact-ID disposable persisted session.",
        trials=turns, fixture_commit=fixture_commit, version=version, os_name=os_name,
        source_commit=source_commit, date=date,
    )
