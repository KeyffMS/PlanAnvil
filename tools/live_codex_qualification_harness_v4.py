from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import qualification_c09 as c09
import qualification_c08 as c08

import live_codex_qualification_harness as v1
import live_codex_qualification_harness_v2 as v2
import live_codex_qualification_harness_v3 as prior

base = prior.base

TARGET_CAPABILITIES = {"C06", "C08", "C09"}
_ORIGINAL_CAPABILITY_RUNTIME = prior.capability_runtime

C08_COMPACT_LIMIT = c08.COMPACT_LIMIT
C09_COMPACT_LIMIT = c09.COMPACT_LIMIT
COMPACT_SCOPE = "body_after_prefix"
HOOK_LOG_RELATIVE = ".pursue/qualification-hook-events.jsonl"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _runtime_paths(
    *, root: Path, runtime_root: Path, capability_id: str
) -> tuple[Path, Path, Path, Path, Path, Path, Path]:
    return v2._runtime_paths(root=root, runtime_root=runtime_root, capability_id=capability_id)


def _hook_proxy_source() -> str:
    return r'''from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

event_name, script_name = sys.argv[1], sys.argv[2]
raw = sys.stdin.read()
try:
    event = json.loads(raw) if raw.strip() else {}
except json.JSONDecodeError:
    event = {}
root = Path(subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"], text=True
).strip())
script = root / ".codex" / "hooks" / script_name
completed = subprocess.run(
    [sys.executable, str(script)],
    input=raw,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=False,
)
record = {
    "event": event_name,
    "returncode": completed.returncode,
}
if isinstance(event, dict):
    tool_name = event.get("tool_name")
    if isinstance(tool_name, str) and tool_name:
        record["tool_name"] = tool_name
try:
    parsed = json.loads(completed.stdout) if completed.stdout.strip() else {}
except json.JSONDecodeError:
    parsed = {}
if isinstance(parsed, dict):
    if "continue" in parsed:
        record["continue"] = parsed.get("continue")
    stop_reason = parsed.get("stopReason")
    if isinstance(stop_reason, str):
        lowered = stop_reason.lower()
        record["stop_reason_mentions_checkpoint"] = "checkpoint" in lowered
        record["stop_reason_mentions_recovery"] = "recovery" in lowered or "canonical state" in lowered
    hook_output = parsed.get("hookSpecificOutput")
    if isinstance(hook_output, dict):
        if hook_output.get("additionalContext"):
            record["additional_context"] = True
        decision = hook_output.get("permissionDecision")
        if isinstance(decision, str):
            record["permission_decision"] = decision
log = root / ".pursue" / "qualification-hook-events.jsonl"
log.parent.mkdir(parents=True, exist_ok=True)
with log.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
sys.stdout.write(completed.stdout)
sys.stderr.write(completed.stderr)
raise SystemExit(completed.returncode)
'''


def _set_compact_config(repo: Path, *, limit: int, scope: str) -> None:
    config_path = repo / ".codex" / "config.toml"
    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    kept = [
        line
        for line in text.splitlines()
        if not re.match(r"^\s*model_auto_compact_token_limit(?:_scope)?\s*=", line)
    ]
    prefix = [
        f"model_auto_compact_token_limit = {limit}",
        f'model_auto_compact_token_limit_scope = "{scope}"',
        "",
    ]
    _write(config_path, "\n".join([*prefix, *kept]).rstrip() + "\n")


def _instrument_hooks(
    repo: Path,
    *,
    event_to_script: dict[str, str],
    compact_limit: int | None = None,
    compact_scope: str | None = None,
    proxy_source: str | None = None,
) -> None:
    hooks_path = repo / ".codex" / "hooks.json"
    hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
    for event_name, script_name in event_to_script.items():
        groups = hooks.get("hooks", {}).get(event_name, [])
        for group in groups:
            for handler in group.get("hooks", []):
                handler["command"] = (
                    'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/'
                    f'qualification-hook-proxy-v4.py" {event_name} {script_name}'
                )
    _write(hooks_path, json.dumps(hooks, indent=2, sort_keys=True) + "\n")
    _write(repo / ".codex" / "hooks" / "qualification-hook-proxy-v4.py",
           _hook_proxy_source() if proxy_source is None else proxy_source)
    if compact_limit is not None:
        _set_compact_config(
            repo,
            limit=compact_limit,
            scope=compact_scope or COMPACT_SCOPE,
        )
    gitignore = repo / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if HOOK_LOG_RELATIVE not in existing:
        with gitignore.open("a", encoding="utf-8") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            handle.write(HOOK_LOG_RELATIVE + "\n")


def _hook_log(repo: Path) -> Path:
    return repo / HOOK_LOG_RELATIVE


def _clear_hook_log(repo: Path) -> None:
    _hook_log(repo).unlink(missing_ok=True)


def _read_hook_records(repo: Path) -> list[dict[str, Any]]:
    path = _hook_log(repo)
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _event_records(records: list[dict[str, Any]], event: str) -> list[dict[str, Any]]:
    return [item for item in records if item.get("event") == event]


def _run_codex_probe(
    *,
    cwd: Path,
    prompt: str,
    schemas: dict[str, Path],
    results_dir: Path,
    position: int,
    sandbox: str,
    compact_limit: int | None = None,
    compact_scope: str | None = None,
    add_dir: Path | None = None,
    timeout: int = 600,
    observe_process: bool = False,
    inspect_payload: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    output = results_dir / f"trial-{position:02d}.json"
    output.unlink(missing_ok=True)
    args = base.common_codex_args(
        cwd=cwd,
        sandbox=sandbox,
        schema=schemas["trial"],
        output=output,
        add_dir=add_dir,
        trust_project=True,
        hook_trust=True,
        ignore_rules=False,
    )
    if compact_limit is not None:
        args += ["-c", f"model_auto_compact_token_limit={compact_limit}"]
        args += [
            "-c",
            f'model_auto_compact_token_limit_scope="{compact_scope or COMPACT_SCOPE}"',
        ]
    args.append(prompt)
    if observe_process:
        from qualification_process import run_observed
        completed = run_observed(args, cwd=cwd, timeout=timeout)
        events = completed.events
        if not events.get("process_cleanup_ok") or events.get("reader_failed"):
            return {}, events, "Codex process cleanup or diagnostic reader failed"
        if completed.timed_out:
            return {}, events, "Codex invocation timed out"
        if completed.returncode != 0:
            return {}, events, f"Codex exited {completed.returncode}; see structural error_categories"
    else:
        # Preserve the established C06/C08 invocation contract, including C08's
        # intentional negative compaction-stop trial. C13 has its own runner.
        try:
            completed = base.run(args, cwd=cwd, check=False, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {}, {"timeout": True}, "Codex invocation timed out"
        events = base.event_summary(completed.stdout)
        if completed.returncode != 0:
            return ({}, events,
                    f"Codex exited {completed.returncode}: {base.sanitize_text(completed.stderr[-2500:])}")
    if not output.is_file():
        return {}, events, "Codex did not produce the structured output file"
    try:
        payload = base.load_json(output)
    except (OSError, json.JSONDecodeError) as exc:
        return {}, events, f"Codex produced invalid structured output: {exc}"
    if not isinstance(payload, dict):
        return {}, events, "Codex structured output was not a JSON object"
    if inspect_payload is not None:
        # Compare in memory before redaction; the callback returns only structural
        # diagnostics. Raw model content is never included in event evidence.
        events["raw_payload_checks"] = inspect_payload(payload)
    return base.sanitize(payload), events, None


def _write_result(
    *,
    root: Path,
    cap_runtime: Path,
    capability_id: str,
    result: str,
    expected_met: bool,
    observations: list[str],
    blocker: str | None,
    summary: str,
    trials: list[dict[str, Any]],
    fixture_commit: str,
    version: str,
    os_name: str,
    source_commit: str,
    date: str,
) -> tuple[str, bool]:
    required = base.write_evidence(
        root=root,
        capability_id=capability_id,
        result=result,
        expected_met=expected_met,
        observations=observations,
        blocker=blocker,
        summary=summary,
        trials=[base.sanitize(item) for item in trials],
        fixture_commit=fixture_commit,
        version=version,
        os_name=os_name,
        source_commit=source_commit,
        date=date,
    )
    base.local_commit(root, capability_id)
    shutil.rmtree(cap_runtime, ignore_errors=True)
    return result, required


def _c06_runtime(
    *,
    root: Path,
    runtime_root: Path,
    schemas: dict[str, Path],
    version: str,
    os_name: str,
    source_commit: str,
    date: str,
) -> tuple[str, bool]:
    capability_id = "C06"
    cap_dir, cap_runtime, spec_dir, repo, worktrees, results_dir, evaluator_dir = _runtime_paths(
        root=root, runtime_root=runtime_root, capability_id=capability_id
    )
    del cap_dir, spec_dir, worktrees, evaluator_dir

    with v2._python_bytecode_disabled():
        base.ensure_git_repo(repo)
        v1._install_plananvil_release(root, repo)
        _instrument_hooks(
            repo,
            event_to_script={"PreToolUse": "plan-anvil-guard.py"},
        )
        _write(repo / "README.md", "C06 deterministic PreToolUse qualification fixture.\n")
        fixture_commit = base.commit_fixture_baseline(repo)
        _clear_hook_log(repo)

        before = base.git_snapshot(repo)
        payload, events, error = _run_codex_probe(
            cwd=repo,
            prompt=(
                "Exercise C06 supported PreToolUse coverage. Use the direct apply_patch tool exactly "
                "once to add `.pursue/c06-supported.txt` containing only `C06_SUPPORTED`. Do not use "
                "a shell command to create that file. Do not inspect or execute hook scripts manually. "
                "After the patch completes, return capability_id C06, trial supported_apply_patch, "
                "outcome PASS, and a minimal assertion that the requested direct file-change tool ran."
            ),
            schemas=schemas,
            results_dir=results_dir,
            position=1,
            sandbox="workspace-write",
            timeout=600,
        )
        after = base.git_snapshot(repo)
        records = _read_hook_records(repo)
        apply_events = [
            item
            for item in _event_records(records, "PreToolUse")
            if item.get("tool_name") == "apply_patch"
        ]
        supported_file = repo / ".pursue" / "c06-supported.txt"
        supported_mutation = supported_file.is_file() and supported_file.read_text(
            encoding="utf-8"
        ).strip() == "C06_SUPPORTED"

        codex_trial = {
            "capability_id": capability_id,
            "trial": "supported_apply_patch",
            "trial_name": "supported_apply_patch",
            "outcome": (
                "BLOCKED" if error or not supported_mutation else ("PASS" if apply_events else "FAIL")
            ),
            "assertions": [
                {
                    "name": "configured_supported_tool_call_produces_pretooluse_observation",
                    "status": (
                        "BLOCKED"
                        if error or not supported_mutation
                        else ("PASS" if apply_events else "FAIL")
                    ),
                    "evidence": (
                        f"supported_mutation={str(supported_mutation).lower()}; "
                        f"apply_patch_pretooluse_events={len(apply_events)}"
                    ),
                }
            ],
            "observations": [
                f"apply_patch_pretooluse_events={len(apply_events)}",
                f"supported_mutation={str(supported_mutation).lower()}",
                f"completed_file_change_items={events.get('completed_file_change_items', 0)}",
                f"invocation_error={error or 'none'}",
            ],
            "blocker": error,
            "event_summary": events,
            "git_before": before,
            "git_after": after,
            "outer_hook_recorder": {
                "real_hook": ".codex/hooks/plan-anvil-guard.py",
                "recorded_pretooluse_events": len(_event_records(records, "PreToolUse")),
                "recorded_apply_patch_events": len(apply_events),
            },
            "model_payload": payload,
        }

        hook_count_before_outer = len(records)
        outer_before = base.git_snapshot(repo)
        with (repo / "README.md").open("a", encoding="utf-8") as handle:
            handle.write("C06_OUTSIDE_HOOK_LIFECYCLE\n")
        outer_after = base.git_snapshot(repo)
        records_after_outer = _read_hook_records(repo)
        status_after_outer = outer_after.get("status") if isinstance(outer_after, dict) else []
        postcondition_detected = any(
            isinstance(line, str) and line.endswith("README.md") for line in (status_after_outer or [])
        )
        no_hook_assumption = len(records_after_outer) == hook_count_before_outer
        outer_trial = {
            "capability_id": capability_id,
            "trial": "outer_non_intercepted_postcondition",
            "trial_name": "outer_non_intercepted_postcondition",
            "outcome": "PASS" if postcondition_detected and no_hook_assumption else "FAIL",
            "assertions": [
                {
                    "name": "equivalent_path_outside_hook_coverage_is_detected_by_postconditions",
                    "status": "PASS" if postcondition_detected and no_hook_assumption else "FAIL",
                    "evidence": (
                        f"git_postcondition_detected={str(postcondition_detected).lower()}; "
                        f"hook_record_count_unchanged={str(no_hook_assumption).lower()}"
                    ),
                }
            ],
            "observations": [
                "mutation_origin=outer qualification harness outside Codex hook lifecycle",
                f"git_postcondition_detected={str(postcondition_detected).lower()}",
                f"hook_record_count_unchanged={str(no_hook_assumption).lower()}",
            ],
            "blocker": None,
            "git_before": outer_before,
            "git_after": outer_after,
        }

    if error or not supported_mutation:
        result = "BLOCKED"
        expected_met = False
        blocker = error or "The direct apply_patch trial did not create the required fixture mutation."
        summary = "C06 blocked because the supported PreToolUse path was not completely exercised."
    elif not apply_events:
        result = "FAILED"
        expected_met = False
        blocker = "Direct apply_patch completed but the real configured PlanAnvil PreToolUse hook was not observed."
        summary = "C06 failed because a supported direct file-change tool bypassed the configured PreToolUse hook."
    elif not (postcondition_detected and no_hook_assumption):
        result = "FAILED"
        expected_met = False
        blocker = "The deterministic outside-hook mutation was not caught by mandatory Git postconditions."
        summary = "C06 failed because defense-in-depth postcondition detection did not catch an unhooked mutation."
    else:
        result = "REPRODUCED"
        expected_met = True
        blocker = None
        summary = "C06 reproduced: real PreToolUse observed direct apply_patch and mandatory Git postconditions caught a controlled mutation outside the hook lifecycle."

    return _write_result(
        root=root,
        cap_runtime=cap_runtime,
        capability_id=capability_id,
        result=result,
        expected_met=expected_met,
        observations=[
            f"apply_patch_pretooluse_events={len(apply_events)}",
            f"supported_mutation={str(supported_mutation).lower()}",
            f"outer_postcondition_detected={str(postcondition_detected).lower()}",
        ],
        blocker=blocker,
        summary=summary,
        trials=[codex_trial, outer_trial],
        fixture_commit=fixture_commit,
        version=version,
        os_name=os_name,
        source_commit=source_commit,
        date=date,
    )


def _start_active_run(
    *,
    root: Path,
    repo: Path,
    worktrees: Path,
    version: str,
    compact_limit: int,
    create_checkpoint: bool,
    segments: int,
    segment_bytes: int,
    prepare_repo: Callable[[Path], None] | None = None,
    hook_proxy_source: str | None = None,
) -> tuple[Path, str]:
    v1._install_plananvil_release(root, repo)
    _instrument_hooks(
        repo,
        event_to_script={
            "PreToolUse": "plan-anvil-guard.py",
            "PreCompact": "plan-anvil-compaction.py",
            "PostCompact": "plan-anvil-recovery.py",
            "SessionStart": "plan-anvil-recovery.py",
        },
        compact_limit=compact_limit,
        compact_scope=COMPACT_SCOPE,
        proxy_source=hook_proxy_source,
    )
    _write(repo / "README.md", "Deterministic PlanAnvil compaction qualification fixture.\n")
    payload_dir = repo / "qualification-payload"
    payload_dir.mkdir(parents=True, exist_ok=True)
    for index in range(1, segments + 1):
        marker = f"SEGMENT-{index:02d}-"
        repeats = max(1, segment_bytes // len(marker))
        text = (marker * repeats)[:segment_bytes]
        _write(payload_dir / f"segment-{index:02d}.txt", text + "\n")
    # Configure the actual root-checkout hook source before any source snapshot,
    # linked worktree, active run or checkpoint exists. Defaults are unchanged.
    if prepare_repo is not None:
        prepare_repo(repo)
    base.git(repo, "add", "-A")
    base.git(repo, "commit", "--allow-empty", "-q", "-m", "Install deterministic compaction fixture")

    destination = worktrees / "planning"
    start = base.run(
        [
            sys.executable,
            ".agents/skills/plan-anvil/scripts/plan_anvil.py",
            "start",
            "--source",
            ".",
            "--destination",
            str(destination),
            "--goal",
            "Qualify deterministic compaction and recovery behavior",
            "--codex-version",
            version,
            "--model",
            base.MODEL,
            "--permission-mode",
            "approval=never; sandbox=workspace-write",
            "--project-trust",
            "TRUSTED",
            "--hook-mode",
            "HOOKS_TRUSTED",
        ],
        cwd=repo,
        check=False,
        timeout=240,
    )
    payload = v1._parse_json_stdout(start, "PlanAnvil start")
    planning = Path(payload["planning_worktree"]).resolve()
    run_root = str(payload["run_root"])
    if create_checkpoint:
        _create_checkpoint(planning=planning, run_root=run_root)
    return planning, run_root


def _create_checkpoint(*, planning: Path, run_root: str) -> None:
    completed = base.run(
        [
            sys.executable,
            ".agents/skills/plan-anvil/scripts/create_generation_checkpoint.py",
            "--planning",
            ".",
            "--run-root",
            run_root,
        ],
        cwd=planning,
        check=False,
        timeout=120,
    )
    v1._parse_json_stdout(completed, "generation checkpoint")


def _checkpoint_validation(planning: Path) -> dict[str, Any]:
    code = r'''import json, sys
from pathlib import Path
sys.path.insert(0, str(Path('.codex/hooks').resolve()))
from plan_anvil_hooklib import active_run_for_event
from plan_anvil_checkpoint import validate_checkpoint_for_run
active = active_run_for_event({"cwd": str(Path.cwd())})
if active is None:
    print(json.dumps({"active_run": False, "ok": False, "reason_count": 1, "reasons": ["active run not found"]}))
else:
    result = validate_checkpoint_for_run(active)
    print(json.dumps({
        "active_run": True,
        "ok": result.ok,
        "reason_count": len(result.reasons),
        "reasons": list(result.reasons),
    }, sort_keys=True))
'''
    completed = base.run([sys.executable, "-B", "-c", code], cwd=planning, check=False, timeout=120)
    if completed.returncode != 0:
        return {
            "active_run": False,
            "ok": False,
            "reason_count": 1,
            "reasons": [base.sanitize_text((completed.stderr or completed.stdout)[-1000:])],
        }
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"active_run": False, "ok": False, "reason_count": 1, "reasons": ["invalid validator output"]}
    return base.sanitize(value) if isinstance(value, dict) else {"ok": False}


def _compact_probe_prompt(capability_id: str, segment_names: list[str]) -> str:
    commands = "\n".join(
        f"- run `cat qualification-payload/{name}` in a separate shell-tool call" for name in segment_names
    )
    return f"""Exercise genuine Codex automatic compaction for {capability_id}.

Do not invoke hook scripts directly, do not simulate hook events, and do not inspect the hook recorder.
Execute these reads in order, continuing normally after any automatic compaction:
{commands}
After the listed reads, run `git status --porcelain=v1 --untracked-files=all` and `git rev-parse HEAD`.
Then return capability_id {capability_id}, a concise trial result, and only relative/boolean observations.
"""


def _c08_runtime(**kwargs: Any) -> tuple[str, bool]:
    root, runtime_root = kwargs["root"], kwargs["runtime_root"]
    capability_id = "C08"
    _, cap_runtime, _, repo, worktrees, results_dir, _ = _runtime_paths(
        root=root, runtime_root=runtime_root, capability_id=capability_id)
    trials = []
    with v2._python_bytecode_disabled():
        base.ensure_git_repo(repo)
        planning, run_root = _start_active_run(
            root=root, repo=repo, worktrees=worktrees, version=kwargs["version"],
            compact_limit=C08_COMPACT_LIMIT, create_checkpoint=False,
            segments=0, segment_bytes=0, prepare_repo=c08.prepare_repo,
            hook_proxy_source=c08.proxy_source(_hook_proxy_source()))
        c08.seed_state(planning, run_root)
        fixture_commit = base.git(repo, "rev-parse", "HEAD")
        for position, repaired in enumerate((False, True), 1):
            # Repair outside the model, between independent invocations, in the
            # SAME canonical run. No product code or decision is replaced.
            if repaired:
                _create_checkpoint(planning=planning, run_root=run_root)
            checkpoint_before = _checkpoint_validation(planning)
            _clear_hook_log(planning)
            before = base.git_snapshot(planning)
            source_before = base.git_snapshot(repo)
            files_before = (c08.file_fingerprint(repo), c08.file_fingerprint(planning))
            payload, events, error = _run_codex_probe(
                cwd=planning, prompt=c08.prompt(repaired=repaired), schemas=kwargs["schemas"],
                results_dir=results_dir, position=position, sandbox="read-only",
                compact_limit=C08_COMPACT_LIMIT, compact_scope=COMPACT_SCOPE,
                timeout=600, observe_process=True)
            after, source_after = base.git_snapshot(planning), base.git_snapshot(repo)
            files_after = (c08.file_fingerprint(repo), c08.file_fingerprint(planning))
            checkpoint_after = _checkpoint_validation(planning)
            records = _read_hook_records(planning)
            checks = c08.protocol_checks(events, records, repaired=repaired)
            checks["checkpoint_state"] = (checkpoint_before.get("active_run") is True
                and checkpoint_after.get("active_run") is True
                and checkpoint_before.get("ok") is repaired and checkpoint_after.get("ok") is repaired)
            checks["source_and_planning_unchanged"] = (before == after and source_before == source_after
                                                      and files_before == files_after)
            trial = c08.REPAIRED_TRIAL if repaired else c08.INVALID_TRIAL
            if repaired:
                checks["completed_positive_output"] = (error is None and payload.get("capability_id") == "C08"
                    and payload.get("trial") == trial and payload.get("outcome") == "PASS"
                    and "C08_FINISHED" in payload.get("observations", []))
            ok = all(checks.values())
            missing = ", ".join(k for k, value in checks.items() if not value)
            assertion = ("checkpoint_blocker_is_repairable_not_permanent" if repaired
                         else "precompact_stops_or_delays_when_recovery_state_is_invalid")
            trials.append({"capability_id": "C08", "trial": trial, "trial_name": trial,
                "outcome": "PASS" if ok else "BLOCKED", "protocol_version": "finite-c08-v1",
                "protocol_checks": checks,
                "assertions": [{"name": assertion, "status": "PASS" if ok else "BLOCKED",
                                "evidence": "finite stop/repair protocol verified" if ok else missing}],
                "observations": ["expected_negative_stop=" + str(not repaired and ok).lower(),
                                 "invocation_error=" + (error or "none")],
                "blocker": None if ok else "C08 incomplete proof: " + missing,
                "event_summary": events, "hook_timeline": records[:80],
                "hook_timeline_truncated": len(records) > 80,
                "git_before": before, "git_after": after,
                "checkpoint_validation": checkpoint_before, "checkpoint_after": checkpoint_after,
                "model_payload": payload, "config_evidence": {
                    "model_auto_compact_token_limit": C08_COMPACT_LIMIT,
                    "model_auto_compact_token_limit_scope": COMPACT_SCOPE,
                    "startup_context_disabled_at_root_before_bootstrap": True}})
    ok = all(t["outcome"] == "PASS" for t in trials)
    return _write_result(root=root, cap_runtime=cap_runtime, capability_id="C08",
        result="REPRODUCED" if ok else "BLOCKED", expected_met=ok,
        observations=["finite_c08_stop_and_repair=" + str(ok).lower()],
        blocker=None if ok else "; ".join(t["blocker"] for t in trials if t["blocker"]),
        summary="C08 finite negative stop and positive repaired completion verified." if ok else "C08 finite proof incomplete.",
        trials=trials, fixture_commit=fixture_commit, version=kwargs["version"],
        os_name=kwargs["os_name"], source_commit=kwargs["source_commit"], date=kwargs["date"])


def _continued_after_second_postcompact(records: list[dict[str, Any]]) -> bool:
    post_indexes = [index for index, item in enumerate(records) if item.get("event") == "PostCompact"]
    if len(post_indexes) < 2:
        return False
    second = post_indexes[1]
    return any(
        index > second and item.get("event") == "PreToolUse"
        for index, item in enumerate(records)
    )


def _c09_runtime(
    *,
    root: Path,
    runtime_root: Path,
    schemas: dict[str, Path],
    version: str,
    os_name: str,
    source_commit: str,
    date: str,
) -> tuple[str, bool]:
    capability_id = "C09"
    cap_dir, cap_runtime, spec_dir, repo, worktrees, results_dir, evaluator_dir = _runtime_paths(
        root=root, runtime_root=runtime_root, capability_id=capability_id
    )
    del cap_dir, spec_dir, evaluator_dir

    with v2._python_bytecode_disabled():
        base.ensure_git_repo(repo)
        planning, _run_root = _start_active_run(
            root=root,
            repo=repo,
            worktrees=worktrees,
            version=version,
            compact_limit=C09_COMPACT_LIMIT,
            create_checkpoint=False,
            segments=0,
            segment_bytes=0,
            prepare_repo=c09.prepare_repo,
            hook_proxy_source=c09.proxy_source(_hook_proxy_source()),
        )
        c09.seed_state(planning, _run_root)
        _create_checkpoint(planning=planning, run_root=_run_root)
        fixture_commit = base.git(repo, "rev-parse", "HEAD")
        checkpoint_before = _checkpoint_validation(planning)
        _clear_hook_log(planning)
        source_before = base.git_snapshot(repo)
        files_before = (c09.file_fingerprint(repo), c09.file_fingerprint(planning))
        before = base.git_snapshot(planning)
        payload, events, error = _run_codex_probe(
            cwd=planning,
            prompt=c09.prompt(),
            schemas=schemas,
            results_dir=results_dir,
            position=1,
            sandbox="read-only",
            compact_limit=C09_COMPACT_LIMIT,
            compact_scope=COMPACT_SCOPE,
            timeout=900,
            observe_process=True,
        )
        after = base.git_snapshot(planning)
        source_after = base.git_snapshot(repo)
        files_after = (c09.file_fingerprint(repo), c09.file_fingerprint(planning))
        records = _read_hook_records(planning)
        pre = _event_records(records, "PreCompact")
        post = _event_records(records, "PostCompact")
        stops = [item for item in pre if item.get("continue") is False]
        checkpoint_after = _checkpoint_validation(planning)

    checks = c09.protocol_checks(events, records)
    checks["source_and_planning_unchanged"] = (source_before == source_after and before == after
                                               and files_before == files_after)
    protocol_ok = all(checks.values())
    two_compactions = len(pre) >= 2 and len(post) >= 2
    continued_after_second = _continued_after_second_postcompact(records)
    checkpoint_coherent = bool(checkpoint_before.get("ok")) and bool(checkpoint_after.get("ok"))
    no_stop_loop = not stops and continued_after_second
    invocation_completed = (
        error is None
        and not events.get("timeout")
        and payload.get("capability_id") == capability_id
        and payload.get("outcome") == "PASS"
        and payload.get("trial") == c09.TRIAL
        and "C09_FINISHED" in payload.get("observations", [])
    )
    completion_blocker = error or (
        None if invocation_completed else "C09 did not return a completed positive structured result."
    )

    trial = {
        "capability_id": capability_id,
        "trial": "checkpoint_auto_compact_recover_recompact",
        "trial_name": "checkpoint_auto_compact_recover_recompact",
        "outcome": (
            "BLOCKED"
            if not invocation_completed or not two_compactions or not protocol_ok
            else ("PASS" if checkpoint_coherent and no_stop_loop else "FAIL")
        ),
        "protocol_checks": checks,
        "assertions": [
            {
                "name": "codex_invocation_completed_without_timeout",
                "status": "PASS" if invocation_completed else "BLOCKED",
                "evidence": f"invocation_completed={str(invocation_completed).lower()}",
            },
            {
                "name": "valid_checkpoint_allows_compaction",
                "status": "PASS" if two_compactions and not stops else ("BLOCKED" if not two_compactions else "FAIL"),
                "evidence": f"precompact={len(pre)}; postcompact={len(post)}; continue_false={len(stops)}",
            },
            {
                "name": "recovery_reconciles_canonical_files_and_git_after_compaction",
                "status": "PASS" if two_compactions and checkpoint_coherent else ("BLOCKED" if not two_compactions else "FAIL"),
                "evidence": (
                    f"checkpoint_before_valid={str(bool(checkpoint_before.get('ok'))).lower()}; "
                    f"checkpoint_after_valid={str(bool(checkpoint_after.get('ok'))).lower()}"
                ),
            },
            {
                "name": "second_valid_compaction_path_is_not_permanently_blocked",
                "status": "PASS" if two_compactions and no_stop_loop and invocation_completed else ("BLOCKED" if not two_compactions or not invocation_completed else "FAIL"),
                "evidence": (
                    f"second_postcompact_observed={str(len(post) >= 2).lower()}; "
                    f"tool_use_after_second_postcompact={str(continued_after_second).lower()}; "
                    f"invocation_completed={str(invocation_completed).lower()}"
                ),
            },
        ],
        "observations": [
            f"precompact_count={len(pre)}",
            f"postcompact_count={len(post)}",
            f"continue_false_count={len(stops)}",
            f"tool_use_after_second_postcompact={str(continued_after_second).lower()}",
            f"checkpoint_before_valid={str(bool(checkpoint_before.get('ok'))).lower()}",
            f"checkpoint_after_valid={str(bool(checkpoint_after.get('ok'))).lower()}",
            f"invocation_error={error or 'none'}",
            f"invocation_completed={str(invocation_completed).lower()}",
        ],
        "blocker": completion_blocker or (None if protocol_ok else "C09 finite protocol checks incomplete"),
        "event_summary": events,
        "hook_timeline": [
            {key: item[key] for key in ("event", "returncode", "continue", "additional_context", "source", "trigger", "c09_phase")
             if key in item}
            for item in records[-128:]
            if item.get("event") in {"PreToolUse", "SessionStart", "PreCompact", "PostCompact"}
        ],
        "hook_timeline_truncated": len(records) > 128,
        "git_before": before,
        "git_after": after,
        "checkpoint_before": checkpoint_before,
        "checkpoint_after": checkpoint_after,
        "model_payload": payload,
        "config_evidence": {
            "model_auto_compact_token_limit": C09_COMPACT_LIMIT,
            "model_auto_compact_token_limit_scope": COMPACT_SCOPE,
            "runtime_cli_override": True,
            "project_trust_method": "persisted_user_config",
            "process_observation": "bounded_structural_jsonl",
            "finite_phases": list(c09.PHASES),
            "tool_max_output_tokens": c09.OUTPUT_TOKENS,
            "canonical_action": "C09_FINITE_RECOVERY",
        },
    }

    if not bool(checkpoint_before.get("ok")):
        result = "BLOCKED"
        expected_met = False
        blocker = "The deterministic C09 fixture did not begin with a valid checkpoint."
        summary = "C09 blocked during deterministic fixture preparation."
    elif not checks["source_and_planning_unchanged"]:
        result, expected_met = "FAILED", False
        blocker = "C09 changed source or planning repository state."
        summary = "C09 failed repository immutability."
    elif not invocation_completed:
        result = "BLOCKED"
        expected_met = False
        blocker = completion_blocker
        summary = "C09 blocked because partial lifecycle observations do not prove successful completion."
    elif not two_compactions:
        result = "BLOCKED"
        expected_met = False
        blocker = error or "The low-limit body-after-prefix trigger did not produce two genuine automatic compactions."
        summary = "C09 blocked because two real compaction cycles were not observed."
    elif stops:
        result = "FAILED"
        expected_met = False
        blocker = "A valid checkpoint produced a PreCompact continue=false stop during C09."
        summary = "C09 failed because a valid checkpoint did not consistently allow compaction."
    elif not bool(checkpoint_after.get("ok")):
        result = "FAILED"
        expected_met = False
        blocker = "Checkpoint/canonical Git validation was no longer coherent after genuine compaction."
        summary = "C09 failed because post-compaction recovery did not preserve canonical checkpoint/Git coherence."
    elif not continued_after_second:
        result = "BLOCKED"
        expected_met = False
        blocker = "Two compactions completed, but no subsequent real tool call demonstrated continuation after the second compaction."
        summary = "C09 blocked because freedom from a permanent stop loop was not fully exercised."
    elif not protocol_ok:
        result, expected_met = "BLOCKED", False
        blocker = "C09 finite protocol was not verified: " + ", ".join(k for k, ok in checks.items() if not ok)
        summary = "C09 lacks a completed ordered two-cycle recovery proof."
    else:
        result = "REPRODUCED"
        expected_met = True
        blocker = None
        summary = "C09 reproduced: two genuine automatic compactions completed from a valid checkpoint, canonical checkpoint/Git state remained coherent, and tool use continued after the second compaction."

    return _write_result(
        root=root,
        cap_runtime=cap_runtime,
        capability_id=capability_id,
        result=result,
        expected_met=expected_met,
        observations=[
            f"precompact_count={len(pre)}",
            f"postcompact_count={len(post)}",
            f"continued_after_second={str(continued_after_second).lower()}",
            f"checkpoint_after_valid={str(bool(checkpoint_after.get('ok'))).lower()}",
            f"invocation_completed={str(invocation_completed).lower()}",
        ],
        blocker=blocker,
        summary=summary,
        trials=[trial],
        fixture_commit=fixture_commit,
        version=version,
        os_name=os_name,
        source_commit=source_commit,
        date=date,
    )


def capability_runtime(**kwargs: Any) -> tuple[str, bool]:
    capability_id = str(kwargs["capability_id"])
    if capability_id not in TARGET_CAPABILITIES:
        return _ORIGINAL_CAPABILITY_RUNTIME(**kwargs)
    common = {key: value for key, value in kwargs.items() if key != "capability_id"}
    if capability_id == "C06":
        return _c06_runtime(**common)
    if capability_id == "C08":
        return _c08_runtime(**common)
    return _c09_runtime(**common)


def main(argv: list[str] | None = None) -> int:
    base.capability_runtime = capability_runtime
    return base.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
