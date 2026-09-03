from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import live_codex_qualification as base
import live_codex_qualification_harness_v4 as v4
import live_codex_qualification_harness_v5 as v5

COMPACT_SCOPE = "body_after_prefix"


def thread_id(stdout: str) -> str | None:
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        value = event.get("thread_id") if isinstance(event, dict) and event.get("type") == "thread.started" else None
        if isinstance(value, str) and base.SESSION_ID_RE.fullmatch(value):
            return value
    return None


def stateful_args(
    *, cwd: Path, schema: Path, output: Path, home: Path, limit: int,
    prompt: str, thread: str | None,
) -> list[str]:
    args = base.common_codex_args(
        cwd=cwd, sandbox="read-only", schema=schema, output=output,
        trust_project=True, hook_trust=True, ignore_rules=False,
    )
    if "--ephemeral" not in args:
        raise base.QualificationError("default args unexpectedly lack --ephemeral")
    args.remove("--ephemeral")
    args += ["-c", f"model_auto_compact_token_limit={limit}"]
    args += ["-c", f'model_auto_compact_token_limit_scope="{COMPACT_SCOPE}"']
    args += ["-c", f"sqlite_home={base.toml_quote(str((home / 'sqlite').resolve()))}"]
    args += ["-c", f"log_dir={base.toml_quote(str((home / 'log').resolve()))}"]
    args += [prompt] if thread is None else ["resume", thread, prompt]
    return args


def turn(
    *, cwd: Path, schemas: dict[str, Path], results: Path, position: int,
    home: Path, limit: int, prompt: str, thread: str | None,
) -> tuple[dict[str, Any], dict[str, Any], str | None, str | None]:
    output = results / f"stateful-{position:02d}.json"
    output.unlink(missing_ok=True)
    env = os.environ.copy()
    env["CODEX_HOME"] = str(home)
    try:
        completed = subprocess.run(
            stateful_args(
                cwd=cwd, schema=schemas["trial"], output=output, home=home,
                limit=limit, prompt=prompt, thread=thread,
            ),
            cwd=cwd, env=env, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=600, check=False,
        )
    except subprocess.TimeoutExpired:
        return {}, {"timeout": True}, "stateful Codex turn timed out", thread
    observed = thread or thread_id(completed.stdout)
    events = base.event_summary(completed.stdout)
    if completed.returncode != 0:
        return {}, events, f"Codex exited {completed.returncode}: {base.sanitize_text(completed.stderr[-2500:])}", observed
    if not output.is_file():
        return {}, events, "Codex did not produce structured stateful output", observed
    try:
        payload = base.load_json(output)
    except (OSError, json.JSONDecodeError) as exc:
        return {}, events, f"invalid stateful output: {exc}", observed
    return base.sanitize(payload) if isinstance(payload, dict) else {}, events, None, observed


def segment_prompt(capability_id: str, number: int) -> str:
    return (
        f"For {capability_id}, run exactly one read-only shell command `cat qualification-payload/segment-{number:02d}.txt`. "
        "Do not invoke hooks manually and do not edit files. Return a minimal PASS result after the command; "
        "do not repeat file content in the final response."
    )


def status_prompt(capability_id: str) -> str:
    return (
        f"For {capability_id}, run `git status --porcelain=v1 --untracked-files=all` and `git rev-parse HEAD` "
        "as separate read-only commands. Do not invoke hooks manually. Return a minimal PASS result."
    )


def recovery_stops(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record for record in records
        if record.get("event") == "PreCompact"
        and record.get("continue") is False
        and (record.get("stop_reason_mentions_checkpoint") or record.get("stop_reason_mentions_recovery"))
    ]


def isolated_home(cap_runtime: Path, name: str):
    return v5._prepare_isolated_codex_home(cap_runtime / name)


def cleanup(home: Path, auth: Path | None, auth_before):
    rollouts = v5._session_rollout_count(home)
    clean, auth_ok = v5._cleanup_isolated_codex_home(home, auth, auth_before)
    return rollouts, clean, auth_ok
