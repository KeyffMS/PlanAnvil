from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
from pathlib import Path
from typing import Any, Callable

import codex_runner_precision_matrix as prior

legacy = prior.legacy
base = prior.base
c13 = prior.c13
MODEL = prior.MODEL
COMPACT_LIMIT = prior.COMPACT_LIMIT
PAYLOAD_WORDS = prior.PAYLOAD_WORDS

VARIANT_NAMES = (
    "project_cli_trust_ephemeral_deny",
    "project_persisted_trust_non_ephemeral_json_deny",
    "project_persisted_trust_non_ephemeral_toml_deny",
    "home_non_ephemeral_json_deny",
    "compact_home_body_after_prefix_single",
    "compact_home_body_after_prefix_two_step",
    "compact_home_total_two_step",
    "subagent_project_autodiscovery_non_ephemeral",
    "subagent_project_declared_non_ephemeral",
    "subagent_home_declared_non_ephemeral",
    "subagent_project_declared_ephemeral",
)

PARENT_THREAD_FAILURE_RE = re.compile(
    r"collab\s+spawn\s+failed:\s+no\s+thread\s+with\s+id",
    re.IGNORECASE,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _hook_script() -> str:
    return r'''from __future__ import annotations
import json, sys
from pathlib import Path
kind = sys.argv[1]
log_path = Path(sys.argv[2])
expected_cwd = Path(sys.argv[3]).resolve()
decision = sys.argv[4]
try:
    event = json.load(sys.stdin)
except Exception:
    event = {}
record = {
    "event": kind,
    "hook_event_name": event.get("hook_event_name"),
    "tool_name": event.get("tool_name"),
    "cwd_matches_repo": Path.cwd().resolve() == expected_cwd,
}
log_path.parent.mkdir(parents=True, exist_ok=True)
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
if kind == "PreToolUse":
    specific = {"hookEventName": "PreToolUse", "permissionDecision": decision}
    if decision == "deny":
        specific["permissionDecisionReason"] = "PLANANVIL_DIAG_PRETOOL_DENY"
    print(json.dumps({"hookSpecificOutput": specific}, sort_keys=True))
else:
    print("{}")
'''


def _subagent_script(token: str) -> str:
    return prior._subagent_script(token)


def _agent_toml() -> str:
    return prior._agent_toml()


def _command(script: Path, *args: str) -> str:
    return prior._command(script, *args)


def _project_trust_toml(repo: Path) -> str:
    return (
        f"[projects.{base.toml_quote(str(repo.resolve()))}]\n"
        'trust_level = "trusted"\n'
    )


def _isolated_home(
    root: Path, name: str, repo: Path, *, persisted_trust: bool = True
) -> tuple[Path, Path | None, Any]:
    home, auth_path, auth_before = c13._prepare_isolated_codex_home(
        root / "isolated-home" / name
    )
    config = "[features]\nhooks = true\n"
    if persisted_trust:
        config += "\n" + _project_trust_toml(repo)
    _write(home / "config.toml", config)
    return home, auth_path, auth_before


def _runtime_args(
    repo: Path,
    prompt: str,
    *,
    home: Path,
    ephemeral: bool,
    sandbox: str = "workspace-write",
    hook_trust: bool = True,
    extra_config: list[str] | None = None,
    cli_trust: bool = False,
    ignore_user_config: bool = False,
) -> list[str]:
    args = ["codex", "exec"]
    if ephemeral:
        args.append("--ephemeral")
    if ignore_user_config:
        args.append("--ignore-user-config")
    args += [
        "--strict-config",
        "--json",
        "--model",
        MODEL,
        "--sandbox",
        sandbox,
        "-c",
        'approval_policy="never"',
        "-c",
        "sandbox_workspace_write.network_access=false",
        "-c",
        "features.hooks=true",
    ]
    if cli_trust:
        args += [
            "-c",
            f"projects.{base.toml_quote(str(repo.resolve()))}.trust_level=\"trusted\"",
        ]
    if hook_trust:
        args.append("--dangerously-bypass-hook-trust")
    for value in extra_config or []:
        args += ["-c", value]
    if not ephemeral:
        args += [
            "-c",
            'history.persistence="none"',
            "-c",
            f"sqlite_home={base.toml_quote(str((home / 'sqlite').resolve()))}",
            "-c",
            f"log_dir={base.toml_quote(str((home / 'log').resolve()))}",
        ]
    args.append(prompt)
    return args


def _execute(
    name: str,
    repo: Path,
    args: list[str],
    *,
    home: Path,
    sidecar: Path,
    timeout: int,
    secret: str | None = None,
) -> tuple[dict[str, Any], str, str]:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(home)
    return prior._execute(
        name,
        repo,
        args,
        env=env,
        timeout=timeout,
        sidecar=sidecar,
        secret=secret,
    )


def _hooks_json(script: Path, log: Path, repo: Path, *, decision: str) -> str:
    session = _command(
        script, "SessionStart", str(log.resolve()), str(repo.resolve()), decision
    )
    pretool = _command(
        script, "PreToolUse", str(log.resolve()), str(repo.resolve()), decision
    )
    return json.dumps(
        {
            "hooks": {
                "SessionStart": [
                    {"hooks": [{"type": "command", "command": session, "timeout": 30}]}
                ],
                "PreToolUse": [
                    {
                        "matcher": "^Bash$",
                        "hooks": [
                            {"type": "command", "command": pretool, "timeout": 30}
                        ],
                    }
                ],
            }
        },
        indent=2,
        sort_keys=True,
    ) + "\n"


def _hooks_toml(script: Path, log: Path, repo: Path, *, decision: str) -> str:
    session = _command(
        script, "SessionStart", str(log.resolve()), str(repo.resolve()), decision
    )
    pretool = _command(
        script, "PreToolUse", str(log.resolve()), str(repo.resolve()), decision
    )
    return (
        "[features]\nhooks = true\n\n"
        "[[hooks.SessionStart]]\n\n"
        "[[hooks.SessionStart.hooks]]\n"
        'type = "command"\n'
        f"command = {json.dumps(session)}\n"
        "timeout = 30\n\n"
        "[[hooks.PreToolUse]]\n"
        'matcher = "^Bash$"\n\n'
        "[[hooks.PreToolUse.hooks]]\n"
        'type = "command"\n'
        f"command = {json.dumps(pretool)}\n"
        "timeout = 30\n"
    )


def _hook_variant(
    root: Path,
    output: Path,
    name: str,
    *,
    source: str,
    representation: str,
    ephemeral: bool,
    cli_trust: bool,
) -> dict[str, Any]:
    repo = root / "fixtures" / name
    legacy._init_repo(repo)
    script = root / "scripts" / f"{name}.py"
    log = output / "sidecars" / f"{name}.jsonl"
    _write(script, _hook_script())
    log.unlink(missing_ok=True)
    home, auth_path, auth_before = _isolated_home(
        root, name, repo, persisted_trust=not cli_trust
    )
    cleanup = auth_unchanged = True

    if source == "project":
        if representation == "json":
            _write(repo / ".codex" / "config.toml", "[features]\nhooks = true\n")
            _write(
                repo / ".codex" / "hooks.json",
                _hooks_json(script, log, repo, decision="deny"),
            )
        else:
            _write(
                repo / ".codex" / "config.toml",
                _hooks_toml(script, log, repo, decision="deny"),
            )
        legacy._git(repo, "add", "-A")
        legacy._git(repo, "commit", "-q", "-m", "seed project hook fixture")
    elif source == "home":
        _write(home / "hooks.json", _hooks_json(script, log, repo, decision="deny"))
    else:
        raise ValueError(source)

    marker = "PLANANVIL_DIAG_HOOK_COMMAND_OK"
    prompt = (
        f"Attempt exactly one real shell tool call running `printf {marker}`. "
        "Do not retry if denied. Do not modify files. Then reply exactly "
        "PLANANVIL_DIAG_HOOK_DONE."
    )
    args = _runtime_args(
        repo,
        prompt,
        home=home,
        ephemeral=ephemeral,
        hook_trust=True,
        cli_trust=cli_trust,
        ignore_user_config=cli_trust,
    )
    try:
        result, stdout, _stderr = _execute(
            name, repo, args, home=home, sidecar=log, timeout=600
        )
    finally:
        cleanup, auth_unchanged = c13._cleanup_isolated_codex_home(
            home, auth_path, auth_before
        )

    records = result["sidecar_records"]
    session_records = [r for r in records if r.get("event") == "SessionStart"]
    pretool_records = [r for r in records if r.get("event") == "PreToolUse"]
    command = prior._command_observation(stdout, marker)
    if pretool_records and not command["marker_output_observed"]:
        status = "DENY_OBSERVED"
    elif session_records and not pretool_records:
        status = "HOOK_CONFIG_LOADED_PRETOOL_MISSING"
    elif not session_records and not pretool_records:
        status = "HOOK_CONFIG_NOT_OBSERVED"
    else:
        status = "DENY_NOT_EFFECTIVE"
    result["probe"] = {
        "hook_source": source,
        "representation": representation,
        "ephemeral": ephemeral,
        "cli_trust": cli_trust,
        "session_start_count": len(session_records),
        "pretool_count": len(pretool_records),
        "command": command,
        "isolated_home_cleanup_verified": cleanup,
        "auth_metadata_unchanged": auth_unchanged,
    }
    result["diagnostic_status"] = status
    return base.sanitize(result)


def _compact_recorder_script() -> str:
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


def _compact_hooks_json(script: Path, log: Path, repo: Path) -> str:
    hooks: dict[str, list[dict[str, Any]]] = {
        "SessionStart": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": _command(
                            script,
                            "SessionStart",
                            str(log.resolve()),
                            str(repo.resolve()),
                        ),
                        "timeout": 30,
                    }
                ]
            }
        ]
    }
    for event in ("PreCompact", "PostCompact"):
        hooks[event] = [
            {
                "matcher": "auto",
                "hooks": [
                    {
                        "type": "command",
                        "command": _command(
                            script, event, str(log.resolve()), str(repo.resolve())
                        ),
                        "timeout": 30,
                    }
                ],
            }
        ]
    return json.dumps({"hooks": hooks}, indent=2, sort_keys=True) + "\n"


def _compact_variant(
    root: Path,
    output: Path,
    name: str,
    *,
    scope: str,
    two_step: bool,
) -> dict[str, Any]:
    repo = root / "fixtures" / name
    legacy._init_repo(repo)
    _write(
        repo / "diag-payload.txt",
        ("PLANANVIL_DIAG_PAYLOAD_WORD " * PAYLOAD_WORDS).strip() + "\n",
    )
    legacy._git(repo, "add", "-A")
    legacy._git(repo, "commit", "-q", "-m", "seed compact payload")

    script = root / "scripts" / f"{name}.py"
    log = output / "sidecars" / f"{name}.jsonl"
    _write(script, _compact_recorder_script())
    log.unlink(missing_ok=True)
    home, auth_path, auth_before = _isolated_home(root, name, repo)
    _write(home / "hooks.json", _compact_hooks_json(script, log, repo))
    cleanup = auth_unchanged = True

    if two_step:
        prompt = (
            "Run `cat diag-payload.txt` as the first shell tool call. After that result, "
            "you MUST make a second separate shell tool call running "
            "`printf PLANANVIL_DIAG_AFTER_COMPACT`. Do not combine commands. Then reply "
            "exactly PLANANVIL_DIAG_COMPACT_DONE."
        )
    else:
        prompt = (
            "Run `cat diag-payload.txt` exactly once, then make no more tool calls and "
            "reply exactly PLANANVIL_DIAG_COMPACT_SINGLE_DONE."
        )
    args = _runtime_args(
        repo,
        prompt,
        home=home,
        ephemeral=False,
        extra_config=[
            f"model_auto_compact_token_limit={COMPACT_LIMIT}",
            f'model_auto_compact_token_limit_scope="{scope}"',
            "features.token_budget=false",
        ],
    )
    try:
        result, stdout, _stderr = _execute(
            name, repo, args, home=home, sidecar=log, timeout=900
        )
    finally:
        cleanup, auth_unchanged = c13._cleanup_isolated_codex_home(
            home, auth_path, auth_before
        )

    records = result["sidecar_records"]
    session = sum(r.get("event") == "SessionStart" for r in records)
    pre = sum(r.get("event") == "PreCompact" for r in records)
    post = sum(r.get("event") == "PostCompact" for r in records)
    second = prior._command_observation(
        stdout, "PLANANVIL_DIAG_AFTER_COMPACT" if two_step else None
    )
    if not session:
        status = "HOME_HOOK_CONFIG_NOT_OBSERVED"
    elif two_step and pre and post:
        status = "COMPACTION_OBSERVED"
    elif two_step:
        status = "COMPACTION_NOT_OBSERVED"
    elif pre or post:
        status = "SINGLE_STEP_COMPACTION_OBSERVED"
    else:
        status = "SINGLE_STEP_NO_COMPACTION"
    result["probe"] = {
        "hook_source": "isolated_home",
        "scope": scope,
        "two_step": two_step,
        "session_start_count": session,
        "precompact_count": pre,
        "postcompact_count": post,
        "command": second,
        "isolated_home_cleanup_verified": cleanup,
        "auth_metadata_unchanged": auth_unchanged,
    }
    result["diagnostic_status"] = status
    return base.sanitize(result)


def _project_agent_config(*, declared: bool) -> str:
    text = (
        "[features]\nhooks = true\nmulti_agent = true\n\n"
        "[agents]\nenabled = true\nmax_concurrent_threads_per_session = 2\n"
    )
    if declared:
        text += (
            "\n[agents.fixture_agent]\n"
            'description = "PlanAnvil precision diagnostic child."\n'
            'config_file = "./agents/fixture-agent.toml"\n'
        )
    return text


def _home_subagent_hooks(script: Path, log: Path, repo: Path) -> str:
    return json.dumps(
        {
            "hooks": {
                "SubagentStart": [
                    {
                        "matcher": "^fixture_agent$",
                        "hooks": [
                            {
                                "type": "command",
                                "command": _command(
                                    script, str(log.resolve()), str(repo.resolve())
                                ),
                                "timeout": 30,
                            }
                        ],
                    }
                ]
            }
        },
        indent=2,
        sort_keys=True,
    ) + "\n"


def _subagent_variant(
    root: Path,
    output: Path,
    name: str,
    *,
    agent_source: str,
    declared: bool,
    ephemeral: bool,
) -> dict[str, Any]:
    repo = root / "fixtures" / name
    legacy._init_repo(repo)
    token = secrets.token_hex(16)
    script = root / "scripts" / f"{name}.py"
    log = output / "sidecars" / f"{name}.jsonl"
    _write(script, _subagent_script(token))
    log.unlink(missing_ok=True)
    home, auth_path, auth_before = _isolated_home(root, name, repo)
    cleanup = auth_unchanged = True
    _write(home / "hooks.json", _home_subagent_hooks(script, log, repo))

    if agent_source == "project":
        _write(
            repo / ".codex" / "config.toml",
            _project_agent_config(declared=declared),
        )
        _write(repo / ".codex" / "agents" / "fixture-agent.toml", _agent_toml())
        legacy._git(repo, "add", "-A")
        legacy._git(repo, "commit", "-q", "-m", "seed project agent fixture")
    elif agent_source == "home":
        config = (home / "config.toml").read_text(encoding="utf-8")
        config += (
            "\n[agents]\nenabled = true\nmax_concurrent_threads_per_session = 2\n"
            "\n[agents.fixture_agent]\n"
            'description = "PlanAnvil precision diagnostic child."\n'
            'config_file = "./agents/fixture-agent.toml"\n'
        )
        _write(home / "config.toml", config)
        _write(home / "agents" / "fixture-agent.toml", _agent_toml())
    else:
        raise ValueError(agent_source)

    prompt = (
        "Start exactly one real configured subagent using spawn_agent with agent_type "
        "exactly `fixture_agent`. Wait for it to finish. Do not use shell or file tools "
        "in the root session. Copy the child's exact single-line response, then append "
        "PLANANVIL_DIAG_SUBAGENT_DONE. Never guess an opaque context value."
    )
    args = _runtime_args(
        repo,
        prompt,
        home=home,
        ephemeral=ephemeral,
        sandbox="read-only",
        extra_config=["features.multi_agent=true", "features.multi_agent_v2=false"],
    )
    rollouts = 0
    try:
        result, stdout, stderr = _execute(
            name,
            repo,
            args,
            home=home,
            sidecar=log,
            timeout=900,
            secret=token,
        )
        if not ephemeral:
            rollouts = c13._session_rollout_count(home)
    finally:
        cleanup, auth_unchanged = c13._cleanup_isolated_codex_home(
            home, auth_path, auth_before
        )

    records = result["sidecar_records"]
    echo = f"PLANANVIL_DIAG_CHILD_CONTEXT_ECHO:{token}" in stdout
    missing = "PLANANVIL_DIAG_CHILD_CONTEXT_MISSING" in stdout
    parent_failure = bool(PARENT_THREAD_FAILURE_RE.search(stdout + "\n" + stderr))
    errors = result.get("event_diagnostics", {}).get("sanitized_errors", [])
    unknown_agent = any(
        "unknown agent_type 'fixture_agent'" in str(value) for value in errors
    )
    if parent_failure:
        status = "PARENT_THREAD_FAILURE"
    elif unknown_agent:
        status = "UNKNOWN_AGENT_TYPE"
    elif records and echo:
        status = "SUBAGENT_CONTEXT_OBSERVED"
    elif records and missing:
        status = "HOOK_OBSERVED_CHILD_CONTEXT_MISSING"
    elif records:
        status = "HOOK_OBSERVED_CHILD_RESULT_UNRESOLVED"
    elif rollouts >= 2:
        status = "CHILD_STARTED_HOOK_NOT_OBSERVED"
    else:
        status = "SUBAGENT_NOT_ESTABLISHED"
    result["probe"] = {
        "agent_source": agent_source,
        "declared_role": declared,
        "ephemeral": ephemeral,
        "required_agent_type": "fixture_agent",
        "hook_record_count": len(records),
        "child_exact_context_echo": echo,
        "child_missing_context": missing,
        "parent_thread_failure": parent_failure,
        "unknown_agent_type": unknown_agent,
        "session_rollouts_created": rollouts,
        "isolated_home_cleanup_verified": cleanup,
        "auth_metadata_unchanged": auth_unchanged,
        "opaque_token_persisted_in_evidence": False,
    }
    result["diagnostic_status"] = status
    return base.sanitize(result)


Runner = Callable[[], dict[str, Any]]


def _run_case(name: str, runner: Runner, output: Path) -> dict[str, Any]:
    return prior._run_case(name, runner, output)


def run_matrix(root: Path, output: Path) -> list[dict[str, Any]]:
    (root / "fixtures").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    cases: list[tuple[str, Runner]] = [
        (
            "project_cli_trust_ephemeral_deny",
            lambda: _hook_variant(
                root,
                output,
                "project_cli_trust_ephemeral_deny",
                source="project",
                representation="json",
                ephemeral=True,
                cli_trust=True,
            ),
        ),
        (
            "project_persisted_trust_non_ephemeral_json_deny",
            lambda: _hook_variant(
                root,
                output,
                "project_persisted_trust_non_ephemeral_json_deny",
                source="project",
                representation="json",
                ephemeral=False,
                cli_trust=False,
            ),
        ),
        (
            "project_persisted_trust_non_ephemeral_toml_deny",
            lambda: _hook_variant(
                root,
                output,
                "project_persisted_trust_non_ephemeral_toml_deny",
                source="project",
                representation="toml",
                ephemeral=False,
                cli_trust=False,
            ),
        ),
        (
            "home_non_ephemeral_json_deny",
            lambda: _hook_variant(
                root,
                output,
                "home_non_ephemeral_json_deny",
                source="home",
                representation="json",
                ephemeral=False,
                cli_trust=False,
            ),
        ),
        (
            "compact_home_body_after_prefix_single",
            lambda: _compact_variant(
                root,
                output,
                "compact_home_body_after_prefix_single",
                scope="body_after_prefix",
                two_step=False,
            ),
        ),
        (
            "compact_home_body_after_prefix_two_step",
            lambda: _compact_variant(
                root,
                output,
                "compact_home_body_after_prefix_two_step",
                scope="body_after_prefix",
                two_step=True,
            ),
        ),
        (
            "compact_home_total_two_step",
            lambda: _compact_variant(
                root,
                output,
                "compact_home_total_two_step",
                scope="total",
                two_step=True,
            ),
        ),
        (
            "subagent_project_autodiscovery_non_ephemeral",
            lambda: _subagent_variant(
                root,
                output,
                "subagent_project_autodiscovery_non_ephemeral",
                agent_source="project",
                declared=False,
                ephemeral=False,
            ),
        ),
        (
            "subagent_project_declared_non_ephemeral",
            lambda: _subagent_variant(
                root,
                output,
                "subagent_project_declared_non_ephemeral",
                agent_source="project",
                declared=True,
                ephemeral=False,
            ),
        ),
        (
            "subagent_home_declared_non_ephemeral",
            lambda: _subagent_variant(
                root,
                output,
                "subagent_home_declared_non_ephemeral",
                agent_source="home",
                declared=True,
                ephemeral=False,
            ),
        ),
        (
            "subagent_project_declared_ephemeral",
            lambda: _subagent_variant(
                root,
                output,
                "subagent_project_declared_ephemeral",
                agent_source="project",
                declared=True,
                ephemeral=True,
            ),
        ),
    ]
    return [_run_case(name, runner, output) for name, runner in cases]


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "3.0",
        "purpose": (
            "Codex 0.152 runtime isolation matrix; diagnostic only, never a release gate"
        ),
        "codex_version": base.codex_version(),
        "model": MODEL,
        "variant_count": len(results),
        "harness_error_count": sum(
            r.get("diagnostic_status") == "HARNESS_ERROR" for r in results
        ),
        "variants": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Codex 0.152 runtime-isolation probes"
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    root, output = args.root.resolve(), args.output.resolve()
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(output, ignore_errors=True)
    root.mkdir(parents=True)
    output.mkdir(parents=True)
    results = run_matrix(root, output)
    _write(
        output / "matrix-summary.json",
        json.dumps(base.sanitize(_summary(results)), indent=2, sort_keys=True) + "\n",
    )
    _write(
        output / "README.txt",
        "PlanAnvil Codex 0.152 runtime isolation matrix (schema 3.0).\n"
        "All non-ephemeral probes use an isolated CODEX_HOME and clean it after the run.\n"
        "Opaque subagent context tokens are redacted; raw transcripts and disposable hook scripts are not uploaded.\n"
        "Variant observations are diagnostic only and never a release gate.\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
