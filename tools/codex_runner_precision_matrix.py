from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

import codex_runner_variant_matrix as legacy

base = legacy.base
c13 = legacy.c13
MODEL = legacy.MODEL
COMPACT_LIMIT = legacy.COMPACT_LIMIT
PAYLOAD_WORDS = legacy.PAYLOAD_WORDS

VARIANT_NAMES = (
    "pretool_json_bash_allow_absolute",
    "pretool_json_bash_deny_absolute",
    "pretool_toml_bash_deny_absolute",
    "pretool_json_bash_trusted_no_bypass_absolute",
    "pretool_feature_disabled_control_absolute",
    "compact_body_after_prefix_single_absolute",
    "compact_body_after_prefix_two_step_absolute",
    "compact_total_two_step_absolute",
    "subagent_ephemeral_project_explicit",
    "subagent_non_ephemeral_project_explicit",
    "subagent_non_ephemeral_home_explicit",
)

PARENT_THREAD_FAILURE_RE = re.compile(
    r"collab\s+spawn\s+failed:\s+no\s+thread\s+with\s+id",
    re.IGNORECASE,
)


def _redact(value: Any, secret: str | None) -> Any:
    if not secret:
        return value
    if isinstance(value, str):
        return value.replace(secret, "<context-token>")
    if isinstance(value, list):
        return [_redact(item, secret) for item in value]
    if isinstance(value, dict):
        return {key: _redact(item, secret) for key, item in value.items()}
    return value


def _command_observation(stdout: str, marker: str | None) -> dict[str, Any]:
    completed = 0
    failed = 0
    exit_codes: list[int] = []
    marker_output_observed = False
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "command_execution":
            continue
        if item.get("status") == "completed":
            completed += 1
        elif item.get("status") == "failed":
            failed += 1
        if isinstance(item.get("exit_code"), int):
            exit_codes.append(item["exit_code"])
        output = item.get("aggregated_output")
        if marker and isinstance(output, str) and marker in output:
            marker_output_observed = True
    return {
        "completed_count": completed,
        "failed_count": failed,
        "exit_codes": exit_codes[:8],
        "marker_output_observed": marker_output_observed,
    }


def _pretool_script() -> str:
    return r'''from __future__ import annotations
import json, sys
from pathlib import Path
log_path = Path(sys.argv[1])
expected_cwd = Path(sys.argv[2]).resolve()
decision = sys.argv[3]
try:
    event = json.load(sys.stdin)
except Exception:
    event = {}
record = {
    "event": "PreToolUse",
    "tool_name": event.get("tool_name"),
    "has_tool_input": bool(event.get("tool_input")),
    "cwd_matches_repo": Path.cwd().resolve() == expected_cwd,
    "decision": decision,
}
log_path.parent.mkdir(parents=True, exist_ok=True)
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
specific = {"hookEventName": "PreToolUse", "permissionDecision": decision}
if decision == "deny":
    specific["permissionDecisionReason"] = "PLANANVIL_DIAG_PRETOOL_DENY"
print(json.dumps({"hookSpecificOutput": specific}, sort_keys=True))
'''


def _compact_script() -> str:
    return r'''from __future__ import annotations
import json, sys
from pathlib import Path
event_name = sys.argv[1]
log_path = Path(sys.argv[2])
expected_cwd = Path(sys.argv[3]).resolve()
try:
    event = json.load(sys.stdin)
except Exception:
    event = {}
record = {
    "event": event_name,
    "trigger": event.get("trigger"),
    "cwd_matches_repo": Path.cwd().resolve() == expected_cwd,
}
log_path.parent.mkdir(parents=True, exist_ok=True)
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
print("{}")
'''


def _subagent_script(token: str) -> str:
    return f'''from __future__ import annotations
import json, sys
from pathlib import Path
TOKEN = {token!r}
log_path = Path(sys.argv[1])
expected_cwd = Path(sys.argv[2]).resolve()
try:
    event = json.load(sys.stdin)
except Exception:
    event = {{}}
record = {{
    "event": "SubagentStart",
    "agent_type": event.get("agent_type"),
    "cwd_matches_repo": Path.cwd().resolve() == expected_cwd,
    "additional_context_injected": True,
    "continue_false_returned": True,
}}
log_path.parent.mkdir(parents=True, exist_ok=True)
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\\n")
print(json.dumps({{
    "continue": False,
    "hookSpecificOutput": {{
        "hookEventName": "SubagentStart",
        "additionalContext": "PLANANVIL_DIAG_CONTEXT_TOKEN=" + TOKEN,
    }},
}}, sort_keys=True))
'''


def _agent_toml() -> str:
    return '''name = "fixture_agent"
description = "PlanAnvil precision diagnostic child."
sandbox_mode = "read-only"
developer_instructions = """
Do not use tools. Inspect only your already-active startup/developer context.
If it contains a line beginning `PLANANVIL_DIAG_CONTEXT_TOKEN=`, reply exactly
`PLANANVIL_DIAG_CHILD_CONTEXT_ECHO:<value>` where <value> is the exact opaque
value after the equals sign. If no such line exists, reply exactly
`PLANANVIL_DIAG_CHILD_CONTEXT_MISSING`. Never guess the value.
"""
'''


def _command(script: Path, *args: str) -> str:
    return " ".join(["python3", shlex.quote(str(script.resolve())), *(shlex.quote(arg) for arg in args)])


def _seed_pretool(
    repo: Path,
    script: Path,
    log: Path,
    *,
    representation: str,
    decision: str,
) -> None:
    command = _command(script, str(log.resolve()), str(repo.resolve()), decision)
    if representation == "json":
        legacy._write(
            repo / ".codex" / "hooks.json",
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "^Bash$",
                                "hooks": [{"type": "command", "command": command, "timeout": 30}],
                            }
                        ]
                    }
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
    else:
        legacy._write(
            repo / ".codex" / "config.toml",
            "[features]\nhooks = true\n\n"
            "[[hooks.PreToolUse]]\nmatcher = \"^Bash$\"\n\n"
            "[[hooks.PreToolUse.hooks]]\ntype = \"command\"\n"
            f"command = {json.dumps(command)}\ntimeout = 30\n",
        )
    legacy._git(repo, "add", "-A")
    legacy._git(repo, "commit", "-q", "-m", "seed precision pretool")


def _seed_compact(repo: Path, script: Path, log: Path) -> None:
    hooks: dict[str, list[dict[str, Any]]] = {}
    for event in ("PreCompact", "PostCompact"):
        hooks[event] = [
            {
                "matcher": "auto",
                "hooks": [
                    {
                        "type": "command",
                        "command": _command(script, event, str(log.resolve()), str(repo.resolve())),
                        "timeout": 30,
                    }
                ],
            }
        ]
    legacy._write(repo / ".codex" / "hooks.json", json.dumps({"hooks": hooks}, indent=2, sort_keys=True) + "\n")
    legacy._write(repo / "diag-payload.txt", ("PLANANVIL_DIAG_PAYLOAD_WORD " * PAYLOAD_WORDS).strip() + "\n")
    legacy._git(repo, "add", "-A")
    legacy._git(repo, "commit", "-q", "-m", "seed precision compact")


def _seed_subagent(repo: Path, script: Path, log: Path, *, project_agent: bool) -> None:
    legacy._write(
        repo / ".codex" / "config.toml",
        "[features]\nhooks = true\nmulti_agent = true\n\n"
        "[agents]\nenabled = true\nmax_concurrent_threads_per_session = 2\n",
    )
    if project_agent:
        legacy._write(repo / ".codex" / "agents" / "fixture_agent.toml", _agent_toml())
    legacy._write(
        repo / ".codex" / "hooks.json",
        json.dumps(
            {
                "hooks": {
                    "SubagentStart": [
                        {
                            "matcher": "^fixture_agent$",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": _command(script, str(log.resolve()), str(repo.resolve())),
                                    "timeout": 30,
                                }
                            ],
                        }
                    ]
                }
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    legacy._git(repo, "add", "-A")
    legacy._git(repo, "commit", "-q", "-m", "seed precision subagent")


def _execute(
    name: str,
    repo: Path,
    args: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: int,
    sidecar: Path,
    secret: str | None = None,
) -> tuple[dict[str, Any], str, str]:
    before = legacy._snapshot(repo)
    started = time.monotonic()
    timed_out = False
    try:
        completed = legacy._run(args, cwd=repo, env=env, timeout=timeout)
        rc, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        rc = None
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
    result = {
        "variant": name,
        "duration_seconds": round(time.monotonic() - started, 3),
        "timed_out": timed_out,
        "returncode": rc,
        "repository_unchanged": before == legacy._snapshot(repo),
        "event_diagnostics": _redact(legacy._event_diagnostics(stdout), secret),
        "stderr_tail": _redact(base.sanitize_text(stderr[-3000:]), secret),
        "sidecar_records": legacy._read_jsonl(sidecar),
    }
    return base.sanitize(result), stdout, stderr


def _hook_variant(
    root: Path,
    output: Path,
    name: str,
    representation: str,
    decision: str,
    bypass: bool,
    hooks_enabled: bool,
) -> dict[str, Any]:
    repo = root / "fixtures" / name
    legacy._init_repo(repo)
    script = root / "scripts" / f"{name}.py"
    log = output / "sidecars" / f"{name}.jsonl"
    legacy._write(script, _pretool_script())
    log.unlink(missing_ok=True)
    _seed_pretool(repo, script, log, representation=representation, decision=decision)
    marker = "PLANANVIL_DIAG_HOOK_COMMAND_OK"
    args = legacy._codex_args(
        repo,
        f"Attempt exactly one real shell tool call running `printf {marker}`. Do not retry if denied. Do not modify files. Then reply exactly PLANANVIL_DIAG_HOOK_DONE.",
        bypass_hook_trust=bypass,
        hooks_enabled=hooks_enabled,
    )
    result, stdout, _ = _execute(name, repo, args, timeout=600, sidecar=log)
    records = result["sidecar_records"]
    command = _command_observation(stdout, marker)
    result["probe"] = {
        "representation": representation,
        "decision": decision,
        "bypass_hook_trust": bypass,
        "hooks_enabled": hooks_enabled,
        "hook_record_count": len(records),
        "command": command,
    }
    if not hooks_enabled:
        result["diagnostic_status"] = "CONTROL_OK" if not records and command["marker_output_observed"] else "CONTROL_UNEXPECTED"
    elif decision == "deny":
        result["diagnostic_status"] = "DENY_OBSERVED" if records and not command["marker_output_observed"] else "DENY_NOT_OBSERVED"
    else:
        result["diagnostic_status"] = "ALLOW_OBSERVED" if records and command["marker_output_observed"] else "ALLOW_NOT_OBSERVED"
    return base.sanitize(result)


def _compact_variant(root: Path, output: Path, name: str, scope: str, two_step: bool) -> dict[str, Any]:
    repo = root / "fixtures" / name
    legacy._init_repo(repo)
    script = root / "scripts" / f"{name}.py"
    log = output / "sidecars" / f"{name}.jsonl"
    legacy._write(script, _compact_script())
    log.unlink(missing_ok=True)
    _seed_compact(repo, script, log)
    prompt = (
        "Run `cat diag-payload.txt` as the first shell tool call. After that result, you MUST make a second separate shell tool call running `printf PLANANVIL_DIAG_AFTER_COMPACT`. Do not combine commands. Then reply exactly PLANANVIL_DIAG_COMPACT_DONE."
        if two_step
        else "Run `cat diag-payload.txt` exactly once, then make no more tool calls and reply exactly PLANANVIL_DIAG_COMPACT_SINGLE_DONE."
    )
    args = legacy._codex_args(
        repo,
        prompt,
        hooks_enabled=True,
        extra_config=[
            f"model_auto_compact_token_limit={COMPACT_LIMIT}",
            f'model_auto_compact_token_limit_scope="{scope}"',
            "features.token_budget=false",
        ],
    )
    result, stdout, _ = _execute(name, repo, args, timeout=900, sidecar=log)
    records = result["sidecar_records"]
    pre = sum(item.get("event") == "PreCompact" for item in records)
    post = sum(item.get("event") == "PostCompact" for item in records)
    result["probe"] = {
        "scope": scope,
        "two_step": two_step,
        "precompact_count": pre,
        "postcompact_count": post,
        "command": _command_observation(stdout, "PLANANVIL_DIAG_AFTER_COMPACT" if two_step else None),
    }
    result["diagnostic_status"] = (
        "COMPACTION_OBSERVED" if two_step and pre and post
        else "COMPACTION_NOT_OBSERVED" if two_step
        else "SINGLE_STEP_NO_COMPACTION" if not pre and not post
        else "SINGLE_STEP_COMPACTION_OBSERVED"
    )
    return base.sanitize(result)


def _subagent_variant(root: Path, output: Path, name: str, ephemeral: bool, project_agent: bool) -> dict[str, Any]:
    repo = root / "fixtures" / name
    legacy._init_repo(repo)
    token = secrets.token_hex(16)
    script = root / "scripts" / f"{name}.py"
    log = output / "sidecars" / f"{name}.jsonl"
    legacy._write(script, _subagent_script(token))
    log.unlink(missing_ok=True)
    _seed_subagent(repo, script, log, project_agent=project_agent)
    prompt = (
        "Start exactly one real configured subagent using spawn_agent with agent_type exactly `fixture_agent`. Wait for it to finish. Do not use shell or file tools in the root session. Copy the child's exact single-line response, then append PLANANVIL_DIAG_SUBAGENT_DONE. Never guess an opaque context value."
    )
    env = os.environ.copy()
    home = auth = None
    auth_before = None
    cleanup = auth_unchanged = True
    rollouts = 0
    extra = ["features.multi_agent=true", "features.multi_agent_v2=false"]
    if ephemeral:
        args = legacy._codex_args(repo, prompt, sandbox="read-only", ephemeral=True, hooks_enabled=True, extra_config=extra)
    else:
        home, auth, auth_before = c13._prepare_isolated_codex_home(root / "isolated-home" / name)
        if not project_agent:
            legacy._write(home / "agents" / "fixture_agent.toml", _agent_toml())
        env["CODEX_HOME"] = str(home)
        args = legacy._codex_args(repo, prompt, sandbox="read-only", ephemeral=False, hooks_enabled=True, extra_config=extra)
        args[-1:-1] = [
            "-c", 'history.persistence="none"',
            "-c", f"sqlite_home={base.toml_quote(str((home / 'sqlite').resolve()))}",
            "-c", f"log_dir={base.toml_quote(str((home / 'log').resolve()))}",
        ]
    try:
        result, stdout, stderr = _execute(name, repo, args, env=env, timeout=900, sidecar=log, secret=token)
        if home is not None:
            rollouts = c13._session_rollout_count(home)
    finally:
        if home is not None:
            cleanup, auth_unchanged = c13._cleanup_isolated_codex_home(home, auth, auth_before)
    echo = f"PLANANVIL_DIAG_CHILD_CONTEXT_ECHO:{token}" in stdout
    missing = "PLANANVIL_DIAG_CHILD_CONTEXT_MISSING" in stdout
    parent_failure = bool(PARENT_THREAD_FAILURE_RE.search(stdout + "\n" + stderr))
    records = result["sidecar_records"]
    result["probe"] = {
        "ephemeral": ephemeral,
        "agent_source": "project" if project_agent else "isolated_home",
        "required_agent_type": "fixture_agent",
        "hook_record_count": len(records),
        "child_exact_context_echo": echo,
        "child_missing_context": missing,
        "parent_thread_failure": parent_failure,
        "session_rollouts_created": rollouts,
        "isolated_home_cleanup_verified": cleanup,
        "auth_metadata_unchanged": auth_unchanged,
        "opaque_token_persisted_in_evidence": False,
    }
    result["diagnostic_status"] = (
        "PARENT_THREAD_FAILURE" if parent_failure
        else "SUBAGENT_CONTEXT_OBSERVED" if records and echo
        else "HOOK_OBSERVED_CHILD_CONTEXT_MISSING" if records and missing
        else "HOOK_OBSERVED_CHILD_RESULT_UNRESOLVED" if records
        else "SUBAGENT_HOOK_NOT_OBSERVED"
    )
    return base.sanitize(result)


Runner = Callable[[], dict[str, Any]]


def _run_case(name: str, runner: Runner, output: Path) -> dict[str, Any]:
    try:
        result = runner()
    except Exception as exc:
        result = {
            "variant": name,
            "diagnostic_status": "HARNESS_ERROR",
            "harness_error": base.sanitize_text(f"{type(exc).__name__}: {exc}")[:2000],
            "returncode": None,
            "timed_out": False,
        }
    result["variant"] = name
    safe = base.sanitize(result)
    legacy._write(output / f"{name}.json", json.dumps(safe, indent=2, sort_keys=True) + "\n")
    print(f"{name}: {safe.get('diagnostic_status')} rc={safe.get('returncode')}")
    return safe


def run_matrix(root: Path, output: Path) -> list[dict[str, Any]]:
    (root / "fixtures").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    cases: list[tuple[str, Runner]] = [
        ("pretool_json_bash_allow_absolute", lambda: _hook_variant(root, output, "pretool_json_bash_allow_absolute", "json", "allow", True, True)),
        ("pretool_json_bash_deny_absolute", lambda: _hook_variant(root, output, "pretool_json_bash_deny_absolute", "json", "deny", True, True)),
        ("pretool_toml_bash_deny_absolute", lambda: _hook_variant(root, output, "pretool_toml_bash_deny_absolute", "toml", "deny", True, True)),
        ("pretool_json_bash_trusted_no_bypass_absolute", lambda: _hook_variant(root, output, "pretool_json_bash_trusted_no_bypass_absolute", "json", "allow", False, True)),
        ("pretool_feature_disabled_control_absolute", lambda: _hook_variant(root, output, "pretool_feature_disabled_control_absolute", "json", "deny", True, False)),
        ("compact_body_after_prefix_single_absolute", lambda: _compact_variant(root, output, "compact_body_after_prefix_single_absolute", "body_after_prefix", False)),
        ("compact_body_after_prefix_two_step_absolute", lambda: _compact_variant(root, output, "compact_body_after_prefix_two_step_absolute", "body_after_prefix", True)),
        ("compact_total_two_step_absolute", lambda: _compact_variant(root, output, "compact_total_two_step_absolute", "total", True)),
        ("subagent_ephemeral_project_explicit", lambda: _subagent_variant(root, output, "subagent_ephemeral_project_explicit", True, True)),
        ("subagent_non_ephemeral_project_explicit", lambda: _subagent_variant(root, output, "subagent_non_ephemeral_project_explicit", False, True)),
        ("subagent_non_ephemeral_home_explicit", lambda: _subagent_variant(root, output, "subagent_non_ephemeral_home_explicit", False, False)),
    ]
    return [_run_case(name, runner, output) for name, runner in cases]


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "2.0",
        "purpose": "precision diagnostic-only Codex runner matrix; never a release gate",
        "codex_version": base.codex_version(),
        "model": MODEL,
        "variant_count": len(results),
        "harness_error_count": sum(item.get("diagnostic_status") == "HARNESS_ERROR" for item in results),
        "variants": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run precision Codex 0.152 diagnostics")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    root, output = args.root.resolve(), args.output.resolve()
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(output, ignore_errors=True)
    root.mkdir(parents=True)
    output.mkdir(parents=True)
    results = run_matrix(root, output)
    legacy._write(output / "matrix-summary.json", json.dumps(base.sanitize(_summary(results)), indent=2, sort_keys=True) + "\n")
    legacy._write(
        output / "README.txt",
        "PlanAnvil Codex precision diagnostic matrix (schema 2.0).\n"
        "External hook scripts are disposable and not uploaded. Opaque subagent context tokens are redacted.\n"
        "Variant observations are diagnostic only and never a release gate.\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
