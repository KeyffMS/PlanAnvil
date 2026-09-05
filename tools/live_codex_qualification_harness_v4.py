from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import live_codex_qualification_harness as v1
import live_codex_qualification_harness_v2 as v2
import live_codex_qualification_harness_v3 as prior

base = prior.base

TARGET_CAPABILITIES = {"C06", "C08", "C09"}
_ORIGINAL_CAPABILITY_RUNTIME = prior.capability_runtime

C08_COMPACT_LIMIT = 200
C09_COMPACT_LIMIT = 1000
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
    _write(repo / ".codex" / "hooks" / "qualification-hook-proxy-v4.py", _hook_proxy_source())
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
    try:
        completed = base.run(args, cwd=cwd, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {}, {"timeout": True}, "Codex invocation timed out"
    events = base.event_summary(completed.stdout)
    if completed.returncode != 0:
        return (
            {},
            events,
            f"Codex exited {completed.returncode}: {base.sanitize_text(completed.stderr[-2500:])}",
        )
    if not output.is_file():
        return {}, events, "Codex did not produce the structured output file"
    try:
        payload = base.load_json(output)
    except (OSError, json.JSONDecodeError) as exc:
        return {}, events, f"Codex produced invalid structured output: {exc}"
    if not isinstance(payload, dict):
        return {}, events, "Codex structured output was not a JSON object"
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


def _c08_runtime(
    *,
    root: Path,
    runtime_root: Path,
    schemas: dict[str, Path],
    version: str,
    os_name: str,
    source_commit: str,
    date: str,
) -> tuple[str, bool]:
    capability_id = "C08"
    cap_dir, cap_runtime, spec_dir, repo, worktrees, results_dir, evaluator_dir = _runtime_paths(
        root=root, runtime_root=runtime_root, capability_id=capability_id
    )
    del cap_dir, spec_dir, evaluator_dir

    with v2._python_bytecode_disabled():
        base.ensure_git_repo(repo)
        planning, run_root = _start_active_run(
            root=root,
            repo=repo,
            worktrees=worktrees,
            version=version,
            compact_limit=C08_COMPACT_LIMIT,
            create_checkpoint=False,
            segments=2,
            segment_bytes=32768,
        )
        fixture_commit = base.git(repo, "rev-parse", "HEAD")
        invalid_checkpoint = _checkpoint_validation(planning)
        _clear_hook_log(planning)
        before_invalid = base.git_snapshot(planning)
        payload_invalid, events_invalid, error_invalid = _run_codex_probe(
            cwd=planning,
            prompt=_compact_probe_prompt(capability_id, ["segment-01.txt"]),
            schemas=schemas,
            results_dir=results_dir,
            position=1,
            sandbox="read-only",
            compact_limit=C08_COMPACT_LIMIT,
            compact_scope=COMPACT_SCOPE,
            timeout=600,
        )
        after_invalid = base.git_snapshot(planning)
        invalid_records = _read_hook_records(planning)
        invalid_pre = _event_records(invalid_records, "PreCompact")
        invalid_post = _event_records(invalid_records, "PostCompact")
        stop_records = [
            item
            for item in invalid_pre
            if item.get("continue") is False
            and (item.get("stop_reason_mentions_checkpoint") or item.get("stop_reason_mentions_recovery"))
        ]

        _create_checkpoint(planning=planning, run_root=run_root)
        repaired_checkpoint = _checkpoint_validation(planning)
        _clear_hook_log(planning)
        before_repaired = base.git_snapshot(planning)
        payload_repaired, events_repaired, error_repaired = _run_codex_probe(
            cwd=planning,
            prompt=_compact_probe_prompt(capability_id, ["segment-02.txt"]),
            schemas=schemas,
            results_dir=results_dir,
            position=2,
            sandbox="read-only",
            compact_limit=C08_COMPACT_LIMIT,
            compact_scope=COMPACT_SCOPE,
            timeout=600,
        )
        after_repaired = base.git_snapshot(planning)
        repaired_records = _read_hook_records(planning)
        repaired_pre = _event_records(repaired_records, "PreCompact")
        repaired_post = _event_records(repaired_records, "PostCompact")
        repaired_stops = [item for item in repaired_pre if item.get("continue") is False]

    invalid_triggered = bool(invalid_pre)
    invalid_stopped_for_recovery = bool(stop_records) and not invalid_post
    repair_triggered = bool(repaired_pre) and bool(repaired_post)
    repair_allowed = repair_triggered and not repaired_stops and bool(repaired_checkpoint.get("ok"))

    invalid_trial = {
        "capability_id": capability_id,
        "trial": "automatic_compaction_without_valid_checkpoint",
        "trial_name": "automatic_compaction_without_valid_checkpoint",
        "outcome": (
            "BLOCKED"
            if not invalid_triggered
            else ("PASS" if invalid_stopped_for_recovery else "FAIL")
        ),
        "assertions": [
            {
                "name": "precompact_stops_or_delays_when_recovery_state_is_invalid",
                "status": (
                    "BLOCKED"
                    if not invalid_triggered
                    else ("PASS" if invalid_stopped_for_recovery else "FAIL")
                ),
                "evidence": (
                    f"checkpoint_valid={str(bool(invalid_checkpoint.get('ok'))).lower()}; "
                    f"precompact={len(invalid_pre)}; postcompact={len(invalid_post)}; "
                    f"checkpoint_recovery_stop_records={len(stop_records)}"
                ),
            }
        ],
        "observations": [
            f"precompact_count={len(invalid_pre)}",
            f"postcompact_count={len(invalid_post)}",
            f"stop_records={len(stop_records)}",
            f"invocation_error={error_invalid or 'none'}",
        ],
        "blocker": error_invalid if not invalid_triggered else None,
        "event_summary": events_invalid,
        "git_before": before_invalid,
        "git_after": after_invalid,
        "checkpoint_validation": invalid_checkpoint,
        "model_payload": payload_invalid,
        "config_evidence": {
            "model_auto_compact_token_limit": C08_COMPACT_LIMIT,
            "model_auto_compact_token_limit_scope": COMPACT_SCOPE,
            "runtime_cli_override": True,
        },
    }
    repaired_trial = {
        "capability_id": capability_id,
        "trial": "automatic_compaction_after_checkpoint_repair",
        "trial_name": "automatic_compaction_after_checkpoint_repair",
        "outcome": "PASS" if repair_allowed else ("BLOCKED" if not repair_triggered else "FAIL"),
        "assertions": [
            {
                "name": "checkpoint_blocker_is_repairable_not_permanent",
                "status": "PASS" if repair_allowed else ("BLOCKED" if not repair_triggered else "FAIL"),
                "evidence": (
                    f"checkpoint_valid={str(bool(repaired_checkpoint.get('ok'))).lower()}; "
                    f"precompact={len(repaired_pre)}; postcompact={len(repaired_post)}; "
                    f"continue_false_records={len(repaired_stops)}"
                ),
            }
        ],
        "observations": [
            f"precompact_count={len(repaired_pre)}",
            f"postcompact_count={len(repaired_post)}",
            f"continue_false_records={len(repaired_stops)}",
            f"invocation_error={error_repaired or 'none'}",
        ],
        "blocker": error_repaired if not repair_triggered else None,
        "event_summary": events_repaired,
        "git_before": before_repaired,
        "git_after": after_repaired,
        "checkpoint_validation": repaired_checkpoint,
        "model_payload": payload_repaired,
    }

    if not invalid_triggered:
        result = "BLOCKED"
        expected_met = False
        blocker = error_invalid or "Automatic compaction did not reach the real PreCompact hook with invalid recovery state."
        summary = "C08 blocked because the deterministic automatic-compaction trigger was not observed."
    elif not invalid_stopped_for_recovery:
        result = "FAILED"
        expected_met = False
        blocker = "PreCompact was reached without producing the expected checkpoint/recovery stop decision."
        summary = "C08 failed because invalid recovery state did not produce the documented temporary PreCompact stop."
    elif not repair_triggered:
        result = "BLOCKED"
        expected_met = False
        blocker = error_repaired or "Automatic compaction was not observed after checkpoint repair."
        summary = "C08 blocked because the repaired path did not reach a completed compaction."
    elif not repair_allowed:
        result = "FAILED"
        expected_met = False
        blocker = "A schema-valid repaired checkpoint still caused compaction to stop or fail."
        summary = "C08 failed because the checkpoint/recovery blocker behaved as a permanent compaction disablement."
    else:
        result = "REPRODUCED"
        expected_met = True
        blocker = None
        summary = "C08 reproduced: invalid recovery state stopped real PreCompact with a checkpoint/recovery reason, and compaction succeeded after checkpoint repair."

    return _write_result(
        root=root,
        cap_runtime=cap_runtime,
        capability_id=capability_id,
        result=result,
        expected_met=expected_met,
        observations=[
            f"invalid_precompact={len(invalid_pre)}",
            f"invalid_stop_records={len(stop_records)}",
            f"repaired_postcompact={len(repaired_post)}",
            f"repaired_checkpoint_valid={str(bool(repaired_checkpoint.get('ok'))).lower()}",
        ],
        blocker=blocker,
        summary=summary,
        trials=[invalid_trial, repaired_trial],
        fixture_commit=fixture_commit,
        version=version,
        os_name=os_name,
        source_commit=source_commit,
        date=date,
    )


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
            create_checkpoint=True,
            segments=4,
            segment_bytes=32768,
        )
        fixture_commit = base.git(repo, "rev-parse", "HEAD")
        checkpoint_before = _checkpoint_validation(planning)
        _clear_hook_log(planning)
        before = base.git_snapshot(planning)
        payload, events, error = _run_codex_probe(
            cwd=planning,
            prompt=_compact_probe_prompt(
                capability_id,
                ["segment-01.txt", "segment-02.txt", "segment-03.txt", "segment-04.txt"],
            ),
            schemas=schemas,
            results_dir=results_dir,
            position=1,
            sandbox="read-only",
            compact_limit=C09_COMPACT_LIMIT,
            compact_scope=COMPACT_SCOPE,
            timeout=900,
        )
        after = base.git_snapshot(planning)
        records = _read_hook_records(planning)
        pre = _event_records(records, "PreCompact")
        post = _event_records(records, "PostCompact")
        stops = [item for item in pre if item.get("continue") is False]
        checkpoint_after = _checkpoint_validation(planning)

    two_compactions = len(pre) >= 2 and len(post) >= 2
    continued_after_second = _continued_after_second_postcompact(records)
    checkpoint_coherent = bool(checkpoint_before.get("ok")) and bool(checkpoint_after.get("ok"))
    no_stop_loop = not stops and continued_after_second
    invocation_completed = (
        error is None
        and not events.get("timeout")
        and payload.get("capability_id") == capability_id
        and payload.get("outcome") == "PASS"
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
            if not invocation_completed or not two_compactions
            else ("PASS" if checkpoint_coherent and no_stop_loop else "FAIL")
        ),
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
        "blocker": completion_blocker,
        "event_summary": events,
        "git_before": before,
        "git_after": after,
        "checkpoint_before": checkpoint_before,
        "checkpoint_after": checkpoint_after,
        "model_payload": payload,
        "config_evidence": {
            "model_auto_compact_token_limit": C09_COMPACT_LIMIT,
            "model_auto_compact_token_limit_scope": COMPACT_SCOPE,
            "runtime_cli_override": True,
        },
    }

    if not bool(checkpoint_before.get("ok")):
        result = "BLOCKED"
        expected_met = False
        blocker = "The deterministic C09 fixture did not begin with a valid checkpoint."
        summary = "C09 blocked during deterministic fixture preparation."
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