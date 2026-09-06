from __future__ import annotations

import datetime as dt
import json
import secrets
from pathlib import Path
from typing import Any, Callable, ContextManager

import live_codex_qualification_codex0152 as compat
import live_codex_qualification_harness_v4 as v4
from qualification_c10_observation import echo_diagnostics, proxy_source

base = v4.base
v1 = v4.v1
v2 = v4.v2

C10_COMPACT_LIMIT = 200
C10_SESSION_COMPACT_LIMIT = 1_000_000
C10_SEGMENT_BYTES = 32_768
C10_ECHO_PREFIX = "C10_RECOVERY_ECHO="
C10_TARGET_PREFIX = "evidence/c10-recovery-"
C10_TARGET_SUFFIX = ".json"


def _utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _inject_recovery_probe_state(planning: Path, run_root: str, proof: str) -> None:
    """Seed only an opaque next-action target; product checkpoint code validates the state."""

    state_path = planning / run_root / "state.json"
    state = base.load_json(state_path)
    revision = state.get("revision")
    if not isinstance(revision, int):
        raise base.QualificationError("C10 deterministic state has no integer revision")
    state["revision"] = revision + 1
    state["updated_at"] = _utc_now()
    state["next_action"] = {
        "type": "C10_RECOVERY_PROBE",
        "target": f"{C10_TARGET_PREFIX}{proof}{C10_TARGET_SUFFIX}",
    }
    base.json_dump(state_path, state)


def _set_compaction_trigger(repo: Path) -> None:
    """Prepare the disposable root checkout before the product captures its state."""

    v4._set_compact_config(
        repo,
        limit=C10_COMPACT_LIMIT,
        scope=v4.COMPACT_SCOPE,
    )
    config_path = repo / ".codex" / "config.toml"
    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    config_path.write_text(
        compat._set_feature(text, "token_budget", "false"),
        encoding="utf-8",
    )


def _isolate_compact_session_start(repo: Path) -> bool:
    """Exclude startup context without disabling the documented recovery channel."""
    path = repo / ".codex" / "hooks.json"
    hooks = base.load_json(path)
    configured = hooks.get("hooks", {})
    groups = configured.get("SessionStart", [])
    if not groups or not configured.get("PreCompact") or not configured.get("PostCompact"):
        return False
    for group in groups:
        group["matcher"] = "^compact$"
    base.json_dump(path, hooks)
    return True


def _prepare_postcompact_repo(repo: Path) -> None:
    # Codex rust-v0.153.4 loads linked-worktree hook declarations from the
    # corresponding root checkout. This runs BEFORE commit/start/checkpoint.
    if not _isolate_compact_session_start(repo):
        raise base.QualificationError("C10 could not isolate the root-checkout hook source")
    _set_compaction_trigger(repo)


def _postcompact_hooks_isolated(repo: Path, planning: Path) -> bool:
    source = repo / ".codex" / "hooks.json"
    local = planning / ".codex" / "hooks.json"
    hooks = base.load_json(source).get("hooks", {})
    return (
        source.read_bytes() == local.read_bytes()
        and bool(hooks.get("SessionStart"))
        and all(group.get("matcher") == "^compact$" for group in hooks["SessionStart"])
        and bool(hooks.get("PreCompact"))
        and bool(hooks.get("PostCompact"))
    )


def _redact_proofs(value: Any, proofs: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        for proof in proofs:
            value = value.replace(proof, "<recovery-proof>")
        return value
    if isinstance(value, list):
        return [_redact_proofs(item, proofs) for item in value]
    if isinstance(value, dict):
        return {key: _redact_proofs(item, proofs) for key, item in value.items()}
    return value


def _session_prompt() -> str:
    return f"""Exercise the real C10 SessionStart recovery-context path.

Do not call any tools and do not read any files. Use only context that was already supplied to this
turn by Codex lifecycle hooks. If that context contains a PlanAnvil next-action target matching
`{C10_TARGET_PREFIX}<opaque>{C10_TARGET_SUFFIX}`, copy only the opaque portion into one observation
exactly as `{C10_ECHO_PREFIX}<opaque>` and return capability_id C10, trial
`session_start_recovery_context`, outcome PASS. If no such lifecycle-supplied target is present,
return outcome FAIL. Never invent or guess the opaque value.
"""


def _postcompact_prompt() -> str:
    return f"""Exercise C10 recovery through SessionStart(source=compact) after genuine automatic compaction.

Run exactly one shell-tool command: `cat qualification-payload/segment-01.txt`. Do not combine it
with another command and do not make any other tool call before or after it. Continue normally if
automatic compaction occurs. After that command and any compaction lifecycle, use only context
already supplied by the SessionStart hook for source=compact (not by ordinary startup). If it contains a PlanAnvil next-action target matching
`{C10_TARGET_PREFIX}<opaque>{C10_TARGET_SUFFIX}`, copy only the opaque portion into one observation
exactly as `{C10_ECHO_PREFIX}<opaque>` and return capability_id C10, trial
`postcompact_recovery_context`, outcome PASS. Otherwise return outcome FAIL. Never read `.pursue`,
checkpoint files, state files, hook files, or qualification telemetry, and never invent the value.
"""


def _exact_echo(payload: dict[str, Any], proof: str) -> bool:
    observations = payload.get("observations")
    if not isinstance(observations, list):
        return False
    expected = f"{C10_ECHO_PREFIX}{proof}"
    return any(isinstance(item, str) and item.strip() == expected for item in observations)


def _payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist no opaque recovery value from the model payload."""

    assertions = payload.get("assertions")
    observations = payload.get("observations")
    return {
        "capability_id": payload.get("capability_id"),
        "trial": payload.get("trial"),
        "outcome": payload.get("outcome"),
        "assertion_count": len(assertions) if isinstance(assertions, list) else 0,
        "observation_count": len(observations) if isinstance(observations, list) else 0,
    }


def run_c10(
    *,
    root: Path,
    runtime_root: Path,
    schemas: dict[str, Path],
    version: str,
    os_name: str,
    source_commit: str,
    date: str,
    live_trust_runtime: Callable[[], ContextManager[Path]],
) -> tuple[str, bool]:
    capability_id = "C10"
    (
        _cap_dir,
        cap_runtime,
        _spec_dir,
        repo,
        worktrees,
        results_dir,
        _evaluator_dir,
    ) = v4._runtime_paths(root=root, runtime_root=runtime_root, capability_id=capability_id)

    proof = secrets.token_hex(16)
    compact_proof = secrets.token_hex(16)
    setup_error: str | None = None
    session_error: str | None = None
    compact_error: str | None = None
    session_payload: dict[str, Any] = {}
    compact_payload: dict[str, Any] = {}
    session_events: dict[str, Any] = {}
    compact_events: dict[str, Any] = {}
    session_records: list[dict[str, Any]] = []
    compact_records: list[dict[str, Any]] = []
    before_session: dict[str, Any] = {}
    after_session: dict[str, Any] = {}
    before_compact: dict[str, Any] = {}
    after_compact: dict[str, Any] = {}
    checkpoint_before: dict[str, Any] = {"ok": False}
    checkpoint_after_session: dict[str, Any] = {"ok": False}
    checkpoint_before_compact: dict[str, Any] = {"ok": False}
    checkpoint_after_compact: dict[str, Any] = {"ok": False}
    postcompact_isolated = False
    source_session_unchanged = False
    source_compact_unchanged = False
    fixture_commit = "unavailable"
    compact_fixture_commit = "unavailable"

    try:
        with v2._python_bytecode_disabled():
            base.ensure_git_repo(repo)
            planning, run_root = v4._start_active_run(
                root=root,
                repo=repo,
                worktrees=worktrees,
                version=version,
                compact_limit=C10_SESSION_COMPACT_LIMIT,
                create_checkpoint=False,
                segments=1,
                segment_bytes=C10_SEGMENT_BYTES,
                hook_proxy_source=proxy_source(proof),
            )
            fixture_commit = base.git(repo, "rev-parse", "HEAD")
            _inject_recovery_probe_state(planning, run_root, proof)
            v4._create_checkpoint(planning=planning, run_root=run_root)
            checkpoint_before = v4._checkpoint_validation(planning)
            if not bool(checkpoint_before.get("ok")):
                raise base.QualificationError(
                    "C10 deterministic fixture did not produce a valid product checkpoint"
                )

            with live_trust_runtime():
                v4._clear_hook_log(planning)
                source_before_session = base.git_snapshot(repo)
                before_session = base.git_snapshot(planning)
                session_payload, session_events, session_error = v4._run_codex_probe(
                    cwd=planning,
                    prompt=_session_prompt(),
                    schemas=schemas,
                    results_dir=results_dir,
                    position=1,
                    sandbox="read-only",
                    timeout=600,
                    observe_process=True,
                    inspect_payload=lambda value: echo_diagnostics(value, proof),
                )
                after_session = base.git_snapshot(planning)
                source_session_unchanged = source_before_session == base.git_snapshot(repo)
                session_records = v4._read_hook_records(planning)
                checkpoint_after_session = v4._checkpoint_validation(planning)

                # Independent source checkout and proof: no edits to the first
                # source after bootstrap, and no SessionStart proof carry-over.
                compact_repo = cap_runtime / "postcompact-repo"
                compact_worktrees = worktrees / "postcompact"
                compact_worktrees.mkdir(parents=True, exist_ok=True)
                base.ensure_git_repo(compact_repo)
                compact_planning, compact_run_root = v4._start_active_run(
                    root=root,
                    repo=compact_repo,
                    worktrees=compact_worktrees,
                    version=version,
                    compact_limit=C10_COMPACT_LIMIT,
                    create_checkpoint=False,
                    segments=1,
                    segment_bytes=C10_SEGMENT_BYTES,
                    prepare_repo=_prepare_postcompact_repo,
                    hook_proxy_source=proxy_source(compact_proof),
                )
                compact_fixture_commit = base.git(compact_repo, "rev-parse", "HEAD")
                postcompact_isolated = _postcompact_hooks_isolated(compact_repo, compact_planning)
                if not postcompact_isolated:
                    raise base.QualificationError("C10 root-checkout PostCompact isolation failed")
                _inject_recovery_probe_state(compact_planning, compact_run_root, compact_proof)
                v4._create_checkpoint(planning=compact_planning, run_root=compact_run_root)
                checkpoint_before_compact = v4._checkpoint_validation(compact_planning)
                if not bool(checkpoint_before_compact.get("ok")):
                    raise base.QualificationError("C10 PostCompact fixture checkpoint is invalid")
                v4._clear_hook_log(compact_planning)
                source_before_compact = base.git_snapshot(compact_repo)
                before_compact = base.git_snapshot(compact_planning)
                compact_payload, compact_events, compact_error = v4._run_codex_probe(
                    cwd=compact_planning,
                    prompt=_postcompact_prompt(),
                    schemas=schemas,
                    results_dir=results_dir,
                    position=2,
                    sandbox="read-only",
                    compact_limit=C10_COMPACT_LIMIT,
                    compact_scope=v4.COMPACT_SCOPE,
                    timeout=900,
                    observe_process=True,
                    inspect_payload=lambda value: echo_diagnostics(value, compact_proof),
                )
                after_compact = base.git_snapshot(compact_planning)
                source_compact_unchanged = source_before_compact == base.git_snapshot(compact_repo)
                compact_records = v4._read_hook_records(compact_planning)
                checkpoint_after_compact = v4._checkpoint_validation(compact_planning)
    except Exception as exc:
        setup_error = base.sanitize_text(f"{type(exc).__name__}: {exc}")

    session_start = v4._event_records(session_records, "SessionStart")
    session_context = [item for item in session_start if item.get("additional_context")]
    session_echo = _exact_echo(session_payload, proof)
    session_value_verified = any(
        item.get("returncode") == 0 and item.get("recovery_target_matches_expected") is True
        and item.get("output_event_matches_input") is True for item in session_context
    )
    session_no_tools = (
        int(session_events.get("completed_command_items") or 0) == 0
        and not any(session_events.get("item_types", {}).get(kind, 0)
                    for kind in ("file_change", "mcp_tool_call", "web_search", "collab_tool_call", "other"))
    )
    session_unchanged = bool(before_session) and before_session == after_session and source_session_unchanged
    session_checkpoint_ok = (
        bool(checkpoint_before.get("ok")) and bool(checkpoint_after_session.get("ok"))
    )
    session_ok = (
        setup_error is None
        and session_error is None
        and session_payload.get("outcome") == "PASS"
        and bool(session_context)
        and session_value_verified
        and session_echo
        and session_no_tools
        and session_unchanged
        and session_checkpoint_ok
    )

    precompact = v4._event_records(compact_records, "PreCompact")
    postcompact = v4._event_records(compact_records, "PostCompact")
    compact_session_start = v4._event_records(compact_records, "SessionStart")
    compact_startup = [item for item in compact_session_start if item.get("source") != "compact"]
    post_context = [item for item in compact_session_start
                    if item.get("source") == "compact" and item.get("additional_context")]
    compact_context_ordered = any(
        item in post_context and any(prior_item.get("event") == "PostCompact"
                                    for prior_item in compact_records[:position])
        for position, item in enumerate(compact_records)
    )
    postcompact_output_supported = bool(postcompact) and all(
        item.get("returncode") == 0 and not item.get("additional_context")
        and item.get("product_stdout_is_json") is True
        and item.get("system_message_present") is True
        and item.get("continue") is True
        for item in postcompact
    )
    compact_stops = [item for item in precompact if item.get("continue") is False]
    compact_echo = _exact_echo(compact_payload, compact_proof)
    compact_value_verified = any(
        item.get("returncode") == 0 and item.get("recovery_target_matches_expected") is True
        and item.get("output_event_matches_input") is True for item in post_context
    )
    compact_one_command = (
        int(compact_events.get("completed_command_items") or 0) == 1
        and compact_events.get("command_counts") == {"segment_01": 1}
        and not any(compact_events.get("item_types", {}).get(kind, 0)
                    for kind in ("file_change", "mcp_tool_call", "web_search", "collab_tool_call", "other"))
    )
    compact_unchanged = bool(before_compact) and before_compact == after_compact and source_compact_unchanged
    compact_checkpoint_ok = (
        bool(checkpoint_before_compact.get("ok"))
        and bool(checkpoint_after_compact.get("ok"))
    )
    compact_lifecycle = bool(precompact) and bool(postcompact)
    compact_processes_ok = all(item.get("returncode") == 0 for item in precompact + postcompact)
    compact_ok = (
        setup_error is None
        and compact_error is None
        and compact_payload.get("outcome") == "PASS"
        and postcompact_isolated
        and not compact_startup
        and compact_context_ordered
        and postcompact_output_supported
        and compact_lifecycle
        and compact_processes_ok
        and not compact_stops
        and bool(post_context)
        and compact_value_verified
        and compact_echo
        and compact_one_command
        and compact_unchanged
        and compact_checkpoint_ok
    )

    session_trial = {
        "capability_id": capability_id,
        "trial": "session_start_recovery_context",
        "trial_name": "session_start_recovery_context",
        "outcome": "PASS" if session_ok else ("BLOCKED" if session_error or setup_error else "FAIL"),
        "assertions": [
            {
                "name": "deterministic_product_checkpoint_exists_before_session",
                "status": "PASS" if session_checkpoint_ok else "BLOCKED",
                "evidence": (
                    f"before={str(bool(checkpoint_before.get('ok'))).lower()}; "
                    f"after={str(bool(checkpoint_after_session.get('ok'))).lower()}"
                ),
            },
            {
                "name": "session_start_supplies_recovery_context",
                "status": "PASS" if session_value_verified else ("BLOCKED" if session_error else "FAIL"),
                "evidence": f"session_start={len(session_start)}; context_records={len(session_context)}; expected_target={session_value_verified}",
            },
            {
                "name": "model_receives_opaque_session_recovery_target_without_tools",
                "status": "PASS" if session_echo and session_no_tools else "FAIL",
                "evidence": (
                    f"opaque_echo={str(session_echo).lower()}; "
                    f"command_items={int(session_events.get('completed_command_items') or 0)}"
                ),
            },
            {
                "name": "session_recovery_probe_preserves_repository_state",
                "status": "PASS" if session_unchanged else "FAIL",
                "evidence": f"repository_unchanged={str(session_unchanged).lower()}",
            },
        ],
        "observations": [
            f"session_start_count={len(session_start)}",
            f"session_context_count={len(session_context)}",
            f"opaque_echo_observed={str(session_echo).lower()}",
            f"command_items={int(session_events.get('completed_command_items') or 0)}",
            f"checkpoint_valid={str(session_checkpoint_ok).lower()}",
            f"repository_unchanged={str(session_unchanged).lower()}",
            f"source_worktree_unchanged={str(source_session_unchanged).lower()}",
        ],
        "blocker": session_error or setup_error,
        "event_summary": session_events,
        "checkpoint_before": checkpoint_before,
        "checkpoint_after": checkpoint_after_session,
        "model_payload_summary": _payload_summary(session_payload),
        "value_flow": {
            "hook_emitted_expected_target": session_value_verified,
            "hook_observations": session_context,
            "raw_model": session_events.get("raw_payload_checks", {}),
            "sanitized_model": echo_diagnostics(session_payload, proof),
            "runtime_delivery_proven": session_value_verified and session_echo,
        },
    }

    compact_trial = {
        "capability_id": capability_id,
        "trial": "postcompact_recovery_context",
        "trial_name": "postcompact_recovery_context",
        "outcome": "PASS" if compact_ok else ("BLOCKED" if compact_error or setup_error or not compact_lifecycle else "FAIL"),
        "assertions": [
            {
                "name": "after_compaction_trial_excludes_ordinary_startup_context",
                "status": "PASS" if postcompact_isolated and not compact_startup else "FAIL",
                "evidence": (
                    f"compact_only_matcher={str(postcompact_isolated).lower()}; "
                    f"ordinary_startup_records={len(compact_startup)}"
                ),
            },
            {
                "name": "real_automatic_compaction_reaches_pre_and_post_hooks",
                "status": "PASS" if compact_lifecycle and not compact_stops else ("BLOCKED" if not compact_lifecycle else "FAIL"),
                "evidence": (
                    f"precompact={len(precompact)}; postcompact={len(postcompact)}; "
                    f"continue_false={len(compact_stops)}"
                ),
            },
            {
                "name": "session_start_compact_supplies_recovery_context",
                "status": "PASS" if compact_value_verified else ("BLOCKED" if not compact_lifecycle else "FAIL"),
                "evidence": f"session_start_compact_context_records={len(post_context)}; expected_target={compact_value_verified}",
            },
            {
                "name": "model_receives_opaque_after_compaction_target",
                "status": "PASS" if compact_echo and compact_one_command else "FAIL",
                "evidence": (
                    f"opaque_echo={str(compact_echo).lower()}; "
                    f"command_items={int(compact_events.get('completed_command_items') or 0)}"
                ),
            },
            {
                "name": "checkpoint_remains_coherent_across_compaction",
                "status": "PASS" if compact_checkpoint_ok else "FAIL",
                "evidence": (
                    f"before={str(bool(checkpoint_before_compact.get('ok'))).lower()}; "
                    f"after={str(bool(checkpoint_after_compact.get('ok'))).lower()}"
                ),
            },
            {
                "name": "postcompact_probe_preserves_repository_state",
                "status": "PASS" if compact_unchanged else "FAIL",
                "evidence": f"repository_unchanged={str(compact_unchanged).lower()}",
            },
        ],
        "observations": [
            f"session_start_compact_records={len(compact_session_start)}",
            f"ordinary_startup_records={len(compact_startup)}",
            f"context_after_postcompact={str(compact_context_ordered).lower()}",
            f"precompact_count={len(precompact)}",
            f"postcompact_count={len(postcompact)}",
            f"compact_session_context_count={len(post_context)}",
            f"continue_false_count={len(compact_stops)}",
            f"opaque_echo_observed={str(compact_echo).lower()}",
            f"command_items={int(compact_events.get('completed_command_items') or 0)}",
            f"checkpoint_valid={str(compact_checkpoint_ok).lower()}",
            f"repository_unchanged={str(compact_unchanged).lower()}",
            f"source_worktree_unchanged={str(source_compact_unchanged).lower()}",
        ],
        "blocker": compact_error or setup_error,
        "event_summary": compact_events,
        "checkpoint_before": checkpoint_before_compact,
        "checkpoint_after": checkpoint_after_compact,
        "model_payload_summary": _payload_summary(compact_payload),
        "value_flow": {
            "hook_emitted_expected_target": compact_value_verified,
            "hook_observations": post_context,
            "raw_model": compact_events.get("raw_payload_checks", {}),
            "sanitized_model": echo_diagnostics(compact_payload, compact_proof),
            "runtime_delivery_proven": compact_value_verified and compact_echo,
        },
        "fixture_commit": compact_fixture_commit,
        "config_evidence": {
            "model_auto_compact_token_limit": C10_COMPACT_LIMIT,
            "model_auto_compact_token_limit_scope": v4.COMPACT_SCOPE,
            "token_budget_disabled_in_isolated_fixture": True,
            "startup_context_excluded_with_compact_only_matcher": True,
            "hook_source": "disposable_root_checkout",
            "model_context_event": "SessionStart",
            "model_context_source": "compact",
            "postcompact_output_supported": postcompact_output_supported,
            "compact_hook_processes_ok": compact_processes_ok,
            "configured_before_bootstrap": True,
            "independent_recovery_proof": True,
            "project_trust_method": "persisted_user_config",
        },
    }

    if setup_error or not bool(checkpoint_before.get("ok")):
        result, met = "BLOCKED", False
        blocker = setup_error or "Deterministic C10 product checkpoint setup was invalid."
    elif session_error:
        result, met = "BLOCKED", False
        blocker = session_error
    elif not session_ok:
        result, met = "FAILED", False
        blocker = "Real SessionStart did not provide the validated PlanAnvil recovery context to the model."
    elif compact_error or not compact_lifecycle:
        result, met = "BLOCKED", False
        blocker = compact_error or "Deterministic automatic compaction did not reach both PreCompact and PostCompact."
    elif not compact_ok:
        result, met = "FAILED", False
        if not compact_value_verified:
            blocker = "SessionStart(source=compact) did not emit the expected recovery target; inspect value_flow."
        elif not compact_echo:
            blocker = "SessionStart(source=compact) emitted the expected target, but the exact model echo was not observed; delivery is unproven."
        else:
            blocker = "PostCompact probe did not satisfy isolation, tool-use or state-integrity requirements."
    else:
        result, met, blocker = "REPRODUCED", True, None

    return v4._write_result(
        root=root,
        cap_runtime=cap_runtime,
        capability_id=capability_id,
        result=result,
        expected_met=met,
        observations=[
            "fixture_prepared_by_outer_harness=true",
            f"product_checkpoint_valid={str(bool(checkpoint_before.get('ok'))).lower()}",
            f"session_start_recovery_context={str(session_ok).lower()}",
            f"postcompact_recovery_context={str(compact_ok).lower()}",
            "opaque_recovery_value_persisted=false",
        ],
        blocker=_redact_proofs(blocker, (proof, compact_proof)),
        summary=(
            "C10 reproduced with independent outer-harness-created PlanAnvil runs and product-validated checkpoints; real startup and compact-source SessionStart each supplied recovery context to the model; PostCompact remained advisory."
            if met
            else "C10 deterministic recovery qualification did not completely reproduce both lifecycle context paths."
        ),
        trials=_redact_proofs([session_trial, compact_trial], (proof, compact_proof)),
        fixture_commit=fixture_commit,
        version=version,
        os_name=os_name,
        source_commit=source_commit,
        date=date,
    )


def install(
    v6_module: Any,
    live_trust_runtime: Callable[[], ContextManager[Path]],
) -> None:
    """Route only C10 around the model-authored generic fixture planner."""

    marker = "_plananvil_c10_deterministic_installed"
    if getattr(v6_module, marker, False):
        return
    original_runtime = v6_module._ORIGINAL_CAPABILITY_RUNTIME

    def deterministic_non_target_runtime(**kwargs: Any) -> tuple[str, bool]:
        capability_id = str(kwargs.get("capability_id"))
        if capability_id != "C10":
            return original_runtime(**kwargs)
        common = {key: value for key, value in kwargs.items() if key != "capability_id"}
        return run_c10(live_trust_runtime=live_trust_runtime, **common)

    v6_module._ORIGINAL_CAPABILITY_RUNTIME = deterministic_non_target_runtime
    setattr(v6_module, marker, True)
