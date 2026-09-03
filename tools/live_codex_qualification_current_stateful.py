from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import live_codex_qualification as base
import live_codex_qualification_harness_v5 as v5


def thread_id(stdout: str) -> str:
    ids: list[str] = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "thread.started":
            continue
        value = event.get("thread_id")
        if isinstance(value, str) and base.SESSION_ID_RE.fullmatch(value):
            ids.append(value)
    if len(ids) != 1:
        raise base.QualificationError(f"expected exactly one thread.started id, got {len(ids)}")
    return ids[0]


def stateful_args(
    *, repo: Path, schema: Path, output: Path, home: Path, sandbox: str,
    compact_limit: int, compact_scope: str, prompt: str,
    resume_thread: str | None = None, add_dir: Path | None = None,
) -> list[str]:
    args = base.common_codex_args(
        cwd=repo,
        sandbox=sandbox,
        schema=schema,
        output=output,
        add_dir=add_dir,
        trust_project=True,
        hook_trust=True,
        ignore_rules=False,
    )
    try:
        args.remove("--ephemeral")
    except ValueError as exc:
        raise base.QualificationError("stateful runner expected base args to be ephemeral") from exc
    args += ["-c", f"model_auto_compact_token_limit={compact_limit}"]
    args += ["-c", f'model_auto_compact_token_limit_scope="{compact_scope}"']
    args += ["-c", f"sqlite_home={base.toml_quote(str((home / 'sqlite').resolve()))}"]
    args += ["-c", f"log_dir={base.toml_quote(str((home / 'log').resolve()))}"]
    if resume_thread is None:
        args.append(prompt)
    else:
        if not base.SESSION_ID_RE.fullmatch(resume_thread):
            raise base.QualificationError("resume thread is not an exact Codex thread id")
        args += ["resume", resume_thread, prompt]
    return args


def run_turn(
    *, repo: Path, schemas: dict[str, Path], results_dir: Path, position: int,
    home: Path, sandbox: str, compact_limit: int, compact_scope: str,
    prompt: str, resume_thread: str | None = None, add_dir: Path | None = None,
    timeout: int = 600,
) -> tuple[dict[str, Any], dict[str, Any], str | None, str | None]:
    output = results_dir / f"stateful-{position:02d}.json"
    output.unlink(missing_ok=True)
    args = stateful_args(
        repo=repo,
        schema=schemas["trial"],
        output=output,
        home=home,
        sandbox=sandbox,
        compact_limit=compact_limit,
        compact_scope=compact_scope,
        prompt=prompt,
        resume_thread=resume_thread,
        add_dir=add_dir,
    )
    env = os.environ.copy()
    env["CODEX_HOME"] = str(home)
    try:
        completed = subprocess.run(
            args,
            cwd=repo,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {}, {"timeout": True}, "Codex invocation timed out", resume_thread

    events = base.event_summary(completed.stdout)
    started_thread: str | None = resume_thread
    if resume_thread is None:
        try:
            started_thread = thread_id(completed.stdout)
        except base.QualificationError as exc:
            return {}, events, str(exc), None

    payload: dict[str, Any] = {}
    parse_error: str | None = None
    if output.is_file():
        try:
            value = base.load_json(output)
            if isinstance(value, dict):
                payload = base.sanitize(value)
            else:
                parse_error = "Codex structured output was not a JSON object"
        except (OSError, json.JSONDecodeError) as exc:
            parse_error = f"Codex produced invalid structured output: {exc}"
    elif completed.returncode == 0:
        parse_error = "Codex did not produce the structured output file"

    if completed.returncode != 0:
        error = f"Codex exited {completed.returncode}: {base.sanitize_text(completed.stderr[-2500:])}"
    else:
        error = parse_error
    return payload, events, error, started_thread


def prepare_home(cap_runtime: Path) -> tuple[Path, Path | None, tuple[int, int, int] | None]:
    return v5._prepare_isolated_codex_home(cap_runtime)


def cleanup_home(home: Path, auth_path: Path | None, auth_before: tuple[int, int, int] | None) -> tuple[bool, bool, int]:
    rollouts = v5._session_rollout_count(home)
    cleanup, auth_unchanged = v5._cleanup_isolated_codex_home(home, auth_path, auth_before)
    return cleanup, auth_unchanged, rollouts
