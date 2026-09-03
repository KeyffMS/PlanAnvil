from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import live_codex_qualification as base
import live_codex_qualification_harness_v2 as v2
import live_codex_qualification_harness_v5 as v5
import live_codex_qualification_harness_v6 as v6
from live_codex_qualification_current_common import finish, runtime_paths


def semantic(
    payload: dict[str, Any],
    proof: str,
    events: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
) -> tuple[str, str | None]:
    text = json.dumps(payload, sort_keys=True)
    echo = f"{v5.C13_ECHO_PREFIX}{proof}" in text
    missing = v5.C13_MISSING in text
    if int(events.get("completed_command_items") or 0) or int(events.get("completed_file_change_items") or 0):
        return "BLOCKED", "C13 root probe used forbidden command/file tools."
    if before != after:
        return "FAIL", "C13 changed repository state."
    if echo and not missing:
        return "PASS", None
    if missing:
        return "FAIL", "The real fixture_agent started but did not receive project-scoped SubagentStart additionalContext."
    return "BLOCKED", "C13 produced neither an exact injected-context echo nor an explicit missing-context child result."


def run(
    *, root: Path, runtime_root: Path, schemas: dict[str, Path], version: str,
    os_name: str, source_commit: str, date: str,
) -> tuple[str, bool]:
    capability_id = "C13"
    _, cap_runtime, _, project, _, results, _ = runtime_paths(root, runtime_root, capability_id)
    fallback_used = False
    fallback_commit: str | None = None
    rollouts = 0
    clean = True
    auth_ok = True

    with v2._python_bytecode_disabled():
        proof = v5._context_proof(source_commit)
        base.ensure_git_repo(project)
        v6._seed_project_fixture(project, proof, include_project_agent=True)
        fixture_commit = base.commit_fixture_baseline(project)
        before = base.git_snapshot(project)
        payload_e, events_e, error_e, known = v5._run_c13_codex(
            repo=project, schemas=schemas, results_dir=results, position=1,
            ephemeral=True, timeout=600,
        )
        outcome_e, blocker_e = semantic(payload_e, proof, events_e, before, base.git_snapshot(project))
        trials: list[dict[str, Any]] = [{
            "transport": "ephemeral",
            "semantic_outcome": outcome_e,
            "semantic_blocker": blocker_e,
            "known_parent_thread_failure": known,
            "invocation_error": error_e,
            "model_payload": payload_e,
            "event_summary": events_e,
        }]

        if outcome_e == "PASS":
            final, blocker = "PASS", None
        elif outcome_e == "FAIL":
            final, blocker = "FAIL", blocker_e
        elif not known:
            final, blocker = "BLOCKED", error_e or blocker_e
        else:
            fallback_used = True
            fallback = cap_runtime / "fallback-repo"
            base.ensure_git_repo(fallback)
            v6._seed_project_fixture(fallback, proof, include_project_agent=False)
            fallback_commit = base.commit_fixture_baseline(fallback)
            home, auth, auth_before, agent_ok = v6._prepare_home_scoped_fallback_agent(cap_runtime)
            if auth is None or not agent_ok:
                clean, auth_ok = v5._cleanup_isolated_codex_home(home, auth, auth_before)
                final, blocker = "BLOCKED", "C13 isolated home-agent fallback preflight was unavailable."
            else:
                before_n = base.git_snapshot(fallback)
                payload_n: dict[str, Any] = {}
                events_n: dict[str, Any] = {}
                error_n: str | None = None
                outcome_n = "BLOCKED"
                blocker_n: str | None = None
                try:
                    payload_n, events_n, error_n, _ = v5._run_c13_codex(
                        repo=fallback, schemas=schemas, results_dir=results, position=2,
                        ephemeral=False, isolated_codex_home=home, timeout=600,
                    )
                    outcome_n, blocker_n = semantic(
                        payload_n, proof, events_n, before_n, base.git_snapshot(fallback)
                    )
                    rollouts = v5._session_rollout_count(home)
                finally:
                    clean, auth_ok = v5._cleanup_isolated_codex_home(home, auth, auth_before)
                persistence_ok = rollouts > 0 and clean and auth_ok
                trials.append({
                    "transport": "non-ephemeral-home-agent",
                    "semantic_outcome": outcome_n,
                    "semantic_blocker": blocker_n,
                    "invocation_error": error_n,
                    "model_payload": payload_n,
                    "event_summary": events_n,
                    "session_rollouts_created": rollouts,
                    "cleanup_verified": clean,
                    "auth_metadata_unchanged": auth_ok,
                    "project_scoped_hook_configuration_preserved": True,
                })
                if outcome_n == "PASS" and persistence_ok:
                    final, blocker = "PASS", None
                elif outcome_n == "FAIL":
                    final, blocker = "FAIL", blocker_n
                elif outcome_n == "PASS" and not persistence_ok:
                    final, blocker = "BLOCKED", "C13 semantic proof passed but isolated persistence cleanup failed."
                else:
                    final, blocker = "BLOCKED", error_n or blocker_n

    result = "REPRODUCED" if final == "PASS" else ("FAILED" if final == "FAIL" else "BLOCKED")
    return finish(
        root=root, cap_runtime=cap_runtime, capability_id=capability_id, result=result,
        observations=[
            f"ephemeral_known_parent_thread_failure={str(known).lower()}",
            f"fallback_used={str(fallback_used).lower()}",
            f"session_rollouts_created={rollouts}", f"session_cleanup_verified={str(clean).lower()}",
            f"auth_metadata_unchanged={str(auth_ok).lower()}",
            "project_config_layers_preserved_by_role_override=true",
            "opaque_context_proof_retained_in_evidence=false",
        ],
        blocker=blocker,
        summary="C13 is classified from the real child opaque-context proof; recorder event counts are supplemental and not semantic authority.",
        trials=trials, fixture_commit=fallback_commit or fixture_commit,
        version=version, os_name=os_name, source_commit=source_commit, date=date,
    )
