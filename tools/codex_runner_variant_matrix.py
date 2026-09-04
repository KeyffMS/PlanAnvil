from __future__ import annotations

import argparse
import collections
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import live_codex_qualification as base
import live_codex_qualification_harness_v5 as c13

MODEL = "gpt-5.6-sol"
DIAG_PREFIX = "PLANANVIL_DIAG"
COMPACT_LIMIT = 1200
PAYLOAD_WORDS = 9000

VARIANT_NAMES = (
    "hook_json_bash_bypass",
    "hook_json_exec_command_bypass",
    "hook_toml_bash_bypass",
    "hook_json_bash_trusted_no_bypass",
    "hook_feature_disabled_control",
    "hook_json_bash_sidecar_env",
    "compact_body_after_prefix_no_budget_single",
    "compact_body_after_prefix_no_budget_two_step",
    "compact_body_after_prefix_budget_two_step",
    "compact_total_no_budget_two_step",
    "subagent_v1_explicit",
    "subagent_v2_explicit",
    "subagent_v1_default",
    "subagent_home_non_ephemeral",
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _run(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def _git(repo: Path, *args: str, check: bool = True) -> str:
    completed = _run(["git", *args], cwd=repo, timeout=60)
    if check and completed.returncode != 0:
        raise RuntimeError(base.sanitize_text(completed.stderr[-1000:]))
    return completed.stdout.strip()


def _init_repo(repo: Path) -> None:
    shutil.rmtree(repo, ignore_errors=True)
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "PlanAnvil diagnostic")
    _git(repo, "config", "user.email", "plananvil-diagnostic@example.invalid")
    _git(repo, "config", "commit.gpgsign", "false")
    _write(repo / "README.md", "PlanAnvil Codex runner diagnostic fixture.\n")
    _write(repo / ".gitignore", ".diag/\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "diagnostic fixture")


def _snapshot(repo: Path) -> dict[str, str]:
    return {
        "head": _git(repo, "rev-parse", "HEAD"),
        "status": _git(repo, "status", "--porcelain=v1", "--untracked-files=all"),
    }


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _dedupe(values: list[str], limit: int = 12) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = base.sanitize_text(value.strip())[:1200]
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
        if len(out) >= limit:
            break
    return out


def _event_diagnostics(stdout: str) -> dict[str, Any]:
    event_types: collections.Counter[str] = collections.Counter()
    item_types: collections.Counter[str] = collections.Counter()
    errors: list[str] = []
    markers: list[str] = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        if isinstance(event_type, str):
            event_types[event_type] += 1
        item = event.get("item")
        if isinstance(item, dict):
            item_type = item.get("type")
            if isinstance(item_type, str):
                item_types[item_type] += 1
            values = list(_strings(item))
            if item_type == "error" or event_type == "error":
                errors.extend(values)
            markers.extend(value for value in values if DIAG_PREFIX in value)
        elif event_type == "error":
            errors.extend(_strings(event))
    return {
        "event_types": dict(sorted(event_types.items())),
        "item_types": dict(sorted(item_types.items())),
        "sanitized_errors": _dedupe(errors),
        "diagnostic_markers": _dedupe(markers),
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            out.append(base.sanitize(value))
    return out


def _codex_args(
    repo: Path,
    prompt: str,
    *,
    sandbox: str = "workspace-write",
    ephemeral: bool = True,
    bypass_hook_trust: bool = True,
    hooks_enabled: bool = True,
    extra_config: list[str] | None = None,
) -> list[str]:
    args = ["codex", "exec"]
    if ephemeral:
        args.append("--ephemeral")
    args += [
        "--json",
        "--ignore-user-config",
        "--model",
        MODEL,
        "--sandbox",
        sandbox,
        "-c",
        'approval_policy="never"',
        "-c",
        "sandbox_workspace_write.network_access=false",
        "-c",
        f"projects.{base.toml_quote(str(repo.resolve()))}.trust_level=\"trusted\"",
        "-c",
        f"features.hooks={'true' if hooks_enabled else 'false'}",
    ]
    if bypass_hook_trust:
        args.append("--dangerously-bypass-hook-trust")
    for value in extra_config or []:
        args += ["-c", value]
    args.append(prompt)
    return args


def _pretool_script() -> str:
    return r'''from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path
try:
    event = json.load(sys.stdin)
except Exception:
    event = {}
root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
record = {"event": "PreToolUse", "tool_name": event.get("tool_name"), "has_tool_input": bool(event.get("tool_input"))}
local = root / ".diag" / "pretool.jsonl"
local.parent.mkdir(parents=True, exist_ok=True)
with local.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
sidecar = os.environ.get("PLANANVIL_DIAG_SIDECAR")
if sidecar:
    path = Path(sidecar)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}, sort_keys=True))
'''


def _seed_pretool(repo: Path, *, matcher: str, representation: str) -> None:
    _write(repo / ".codex" / "hooks" / "diag-pretool.py", _pretool_script())
    command = 'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/diag-pretool.py"'
    if representation == "json":
        _write(
            repo / ".codex" / "hooks.json",
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": matcher,
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
    elif representation == "toml":
        _write(
            repo / ".codex" / "config.toml",
            "[features]\nhooks = true\n\n"
            "[[hooks.PreToolUse]]\n"
            f"matcher = {json.dumps(matcher)}\n\n"
            "[[hooks.PreToolUse.hooks]]\n"
            "type = \"command\"\n"
            f"command = {json.dumps(command)}\n"
            "timeout = 30\n",
        )
    else:
        raise ValueError(representation)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"seed {representation} pretool hook")


def _compact_script() -> str:
    return r'''from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
event_name = sys.argv[1]
try:
    event = json.load(sys.stdin)
except Exception:
    event = {}
root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
path = root / ".diag" / "compact.jsonl"
path.parent.mkdir(parents=True, exist_ok=True)
with path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps({"event": event_name, "trigger": event.get("trigger")}, sort_keys=True) + "\n")
print("{}")
'''


def _seed_compaction(repo: Path) -> None:
    _write(repo / ".codex" / "hooks" / "diag-compact.py", _compact_script())
    hooks: dict[str, list[dict[str, Any]]] = {}
    for event in ("PreCompact", "PostCompact"):
        hooks[event] = [
            {
                "matcher": "auto",
                "hooks": [
                    {
                        "type": "command",
                        "command": f'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/diag-compact.py" {event}',
                        "timeout": 30,
                    }
                ],
            }
        ]
    _write(repo / ".codex" / "hooks.json", json.dumps({"hooks": hooks}, indent=2, sort_keys=True) + "\n")
    payload = (("PLANANVIL_DIAG_PAYLOAD_WORD " * PAYLOAD_WORDS).strip() + "\n")
    _write(repo / "diag-payload.txt", payload)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed compaction diagnostic")


def _subagent_hook_script() -> str:
    return r'''from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
try:
    event = json.load(sys.stdin)
except Exception:
    event = {}
root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
path = root / ".diag" / "subagent.jsonl"
path.parent.mkdir(parents=True, exist_ok=True)
with path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps({"event": "SubagentStart", "agent_type": event.get("agent_type")}, sort_keys=True) + "\n")
print(json.dumps({"continue": False, "hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": "PLANANVIL_DIAG_CONTEXT=OK"}}, sort_keys=True))
'''


def _agent_toml() -> str:
    return '''name = "fixture_agent"
description = "PlanAnvil runner diagnostic child."
sandbox_mode = "read-only"
developer_instructions = """
Do not use tools. Inspect your startup/developer context only.
If it contains PLANANVIL_DIAG_CONTEXT=OK reply exactly PLANANVIL_DIAG_CHILD_CONTEXT_OK.
Otherwise reply exactly PLANANVIL_DIAG_CHILD_CONTEXT_MISSING.
"""
'''


def _seed_subagent(repo: Path, *, project_agent: bool) -> None:
    _write(
        repo / ".codex" / "config.toml",
        "[features]\nhooks = true\ncollab = true\n\n[agents]\nenabled = true\nmax_concurrent_threads_per_session = 2\n",
    )
    if project_agent:
        _write(repo / ".codex" / "agents" / "fixture_agent.toml", _agent_toml())
    _write(repo / ".codex" / "hooks" / "diag-subagent.py", _subagent_hook_script())
    _write(
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
                                    "command": 'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/diag-subagent.py"',
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
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed subagent diagnostic")


def _execute_variant(
    name: str,
    repo: Path,
    args: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: int = 600,
    local_logs: tuple[str, ...] = (),
    sidecar: Path | None = None,
) -> dict[str, Any]:
    before = _snapshot(repo)
    started = time.monotonic()
    timed_out = False
    try:
        completed = _run(args, cwd=repo, env=env, timeout=timeout)
        returncode = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = None
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
    after = _snapshot(repo)
    payload = {
        "variant": name,
        "duration_seconds": round(time.monotonic() - started, 3),
        "timed_out": timed_out,
        "returncode": returncode,
        "event_diagnostics": _event_diagnostics(stdout),
        "stderr_tail": base.sanitize_text(stderr[-3000:]),
        "repository_unchanged": before == after,
        "git_before": before,
        "git_after": after,
        "local_hook_records": {
            rel: _read_jsonl(repo / rel) for rel in local_logs
        },
    }
    if sidecar is not None:
        payload["sidecar_records"] = _read_jsonl(sidecar)
    return base.sanitize(payload)


def _hook_variant(root: Path, output: Path, name: str, matcher: str, representation: str, bypass: bool, hooks_enabled: bool, sidecar_env: bool) -> dict[str, Any]:
    repo = root / name
    _init_repo(repo)
    _seed_pretool(repo, matcher=matcher, representation=representation)
    sidecar = output / "sidecars" / f"{name}.jsonl"
    sidecar.unlink(missing_ok=True)
    env = os.environ.copy()
    if sidecar_env:
        env["PLANANVIL_DIAG_SIDECAR"] = str(sidecar.resolve())
    prompt = "Use the real shell tool exactly once to run `printf PLANANVIL_DIAG_HOOK_COMMAND_OK`. Do not modify files. Then reply with PLANANVIL_DIAG_HOOK_DONE."
    args = _codex_args(repo, prompt, bypass_hook_trust=bypass, hooks_enabled=hooks_enabled)
    return _execute_variant(name, repo, args, env=env, local_logs=(".diag/pretool.jsonl",), sidecar=sidecar if sidecar_env else None)


def _compact_variant(root: Path, name: str, scope: str, token_budget: bool, two_step: bool) -> dict[str, Any]:
    repo = root / name
    _init_repo(repo)
    _seed_compaction(repo)
    if two_step:
        prompt = (
            "Run `cat diag-payload.txt` as the first shell tool call. After that result, you MUST make a second separate shell tool call running "
            "`printf PLANANVIL_DIAG_AFTER_COMPACT`. Do not combine the commands. Then reply PLANANVIL_DIAG_COMPACT_DONE."
        )
    else:
        prompt = "Run `cat diag-payload.txt` exactly once, then make no more tool calls and reply PLANANVIL_DIAG_COMPACT_SINGLE_DONE."
    extra = [
        f"model_auto_compact_token_limit={COMPACT_LIMIT}",
        f'model_auto_compact_token_limit_scope="{scope}"',
        f"features.token_budget={'true' if token_budget else 'false'}",
    ]
    args = _codex_args(repo, prompt, hooks_enabled=True, extra_config=extra)
    return _execute_variant(name, repo, args, timeout=900, local_logs=(".diag/compact.jsonl",))


def _subagent_variant(root: Path, output: Path, name: str, v2: bool, explicit: bool, home_non_ephemeral: bool = False) -> dict[str, Any]:
    repo = root / name
    _init_repo(repo)
    _seed_subagent(repo, project_agent=not home_non_ephemeral)
    if explicit:
        prompt = (
            "Start exactly one real configured subagent using spawn_agent with agent_type exactly `fixture_agent`. Wait for it to finish. "
            "Do not use shell or file tools. Copy the child's final PLANANVIL_DIAG marker and then reply PLANANVIL_DIAG_SUBAGENT_DONE."
        )
    else:
        prompt = (
            "Start exactly one real subagent using spawn_agent while omitting agent_type/defaulting the role. Wait for it to finish. "
            "Do not use shell or file tools. Report any sanitized startup error or child PLANANVIL_DIAG marker, then reply PLANANVIL_DIAG_SUBAGENT_DEFAULT_DONE."
        )
    extra = ["features.collab=true", f"features.multi_agent_v2={'true' if v2 else 'false'}"]
    isolated_home: Path | None = None
    auth_path: Path | None = None
    auth_before = None
    cleanup_verified = True
    auth_unchanged = True
    session_rollouts = 0
    env = os.environ.copy()
    if home_non_ephemeral:
        isolated_home, auth_path, auth_before = c13._prepare_isolated_codex_home(output / "isolated-home-runtime" / name)
        _write(isolated_home / "agents" / "fixture_agent.toml", _agent_toml())
        env["CODEX_HOME"] = str(isolated_home)
        args = _codex_args(repo, prompt, sandbox="read-only", ephemeral=False, hooks_enabled=True, extra_config=extra)
        args[-1:-1] = [
            "-c", 'history.persistence="none"',
            "-c", f"sqlite_home={base.toml_quote(str((isolated_home / 'sqlite').resolve()))}",
            "-c", f"log_dir={base.toml_quote(str((isolated_home / 'log').resolve()))}",
        ]
    else:
        args = _codex_args(repo, prompt, sandbox="read-only", ephemeral=True, hooks_enabled=True, extra_config=extra)
    try:
        result = _execute_variant(name, repo, args, env=env, timeout=900, local_logs=(".diag/subagent.jsonl",))
        if isolated_home is not None:
            session_rollouts = c13._session_rollout_count(isolated_home)
    finally:
        if isolated_home is not None:
            cleanup_verified, auth_unchanged = c13._cleanup_isolated_codex_home(isolated_home, auth_path, auth_before)
    result["multi_agent_v2"] = v2
    result["explicit_agent_type"] = explicit
    result["home_non_ephemeral"] = home_non_ephemeral
    result["session_rollouts_created"] = session_rollouts
    result["isolated_home_cleanup_verified"] = cleanup_verified
    result["auth_metadata_unchanged"] = auth_unchanged
    return result


def run_matrix(root: Path, output: Path) -> list[dict[str, Any]]:
    output.mkdir(parents=True, exist_ok=True)
    fixtures = root / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    hook_specs = [
        ("hook_json_bash_bypass", "^Bash$", "json", True, True, False),
        ("hook_json_exec_command_bypass", "^exec_command$", "json", True, True, False),
        ("hook_toml_bash_bypass", "^Bash$", "toml", True, True, False),
        ("hook_json_bash_trusted_no_bypass", "^Bash$", "json", False, True, False),
        ("hook_feature_disabled_control", "^Bash$", "json", True, False, False),
        ("hook_json_bash_sidecar_env", "^Bash$", "json", True, True, True),
    ]
    for spec in hook_specs:
        result = _hook_variant(fixtures, output, *spec)
        results.append(result)
        _write(output / f"{result['variant']}.json", json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(f"{result['variant']}: rc={result['returncode']} hooks={len(result['local_hook_records'].get('.diag/pretool.jsonl', []))}")

    compact_specs = [
        ("compact_body_after_prefix_no_budget_single", "body_after_prefix", False, False),
        ("compact_body_after_prefix_no_budget_two_step", "body_after_prefix", False, True),
        ("compact_body_after_prefix_budget_two_step", "body_after_prefix", True, True),
        ("compact_total_no_budget_two_step", "total", False, True),
    ]
    for spec in compact_specs:
        result = _compact_variant(fixtures, *spec)
        results.append(result)
        _write(output / f"{result['variant']}.json", json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(f"{result['variant']}: rc={result['returncode']} compact={len(result['local_hook_records'].get('.diag/compact.jsonl', []))}")

    subagent_specs = [
        ("subagent_v1_explicit", False, True, False),
        ("subagent_v2_explicit", True, True, False),
        ("subagent_v1_default", False, False, False),
        ("subagent_home_non_ephemeral", False, True, True),
    ]
    for spec in subagent_specs:
        result = _subagent_variant(fixtures, output, *spec)
        results.append(result)
        _write(output / f"{result['variant']}.json", json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(f"{result['variant']}: rc={result['returncode']} subagent_hooks={len(result['local_hook_records'].get('.diag/subagent.jsonl', []))}")

    return results


def _matrix_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "purpose": "diagnostic-only Codex runner variant matrix; never a release gate",
        "codex_version": base.codex_version(),
        "model": MODEL,
        "variant_count": len(results),
        "variants": [
            {
                "variant": item["variant"],
                "returncode": item.get("returncode"),
                "timed_out": item.get("timed_out"),
                "repository_unchanged": item.get("repository_unchanged"),
                "event_diagnostics": item.get("event_diagnostics"),
                "local_hook_records": item.get("local_hook_records"),
                "sidecar_records": item.get("sidecar_records"),
                "session_rollouts_created": item.get("session_rollouts_created"),
                "isolated_home_cleanup_verified": item.get("isolated_home_cleanup_verified"),
                "auth_metadata_unchanged": item.get("auth_metadata_unchanged"),
            }
            for item in results
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run diagnostic Codex 0.152 runner variants without changing release capability results")
    parser.add_argument("--root", type=Path, required=True, help="Disposable runner diagnostic root")
    parser.add_argument("--output", type=Path, required=True, help="Sanitized diagnostic artifact directory")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    output = args.output.resolve()
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    output.mkdir(parents=True, exist_ok=True)
    results = run_matrix(root, output)
    summary = _matrix_summary(results)
    _write(output / "matrix-summary.json", json.dumps(base.sanitize(summary), indent=2, sort_keys=True) + "\n")
    _write(
        output / "README.txt",
        "PlanAnvil Codex runner diagnostic matrix. Results are diagnostic only and do not modify C01-C16 release status.\n"
        "Inspect matrix-summary.json first, then the per-variant JSON files for sanitized errors and hook records.\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
