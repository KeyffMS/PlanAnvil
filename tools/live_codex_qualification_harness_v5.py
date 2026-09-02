from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import live_codex_qualification_harness_v4 as prior

base = prior.base

TARGET_CAPABILITIES = {"C13"}
_ORIGINAL_CAPABILITY_RUNTIME = prior.capability_runtime
C13_HOOK_LOG_RELATIVE = ".pursue/qualification-c13-events.jsonl"
C13_CONTEXT_PREFIX = "C13_CONTEXT_TOKEN="
C13_ECHO_PREFIX = "C13_CONTEXT_ECHO:"
C13_MISSING = "C13_CONTEXT_MISSING"
KNOWN_PARENT_THREAD_FAILURE_RE = re.compile(
    r"collab\s+spawn\s+failed:\s+no\s+thread\s+with\s+id",
    re.IGNORECASE,
)
ALLOW_NON_EPHEMERAL_FALLBACK = False


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _runtime_paths(
    *, root: Path, runtime_root: Path, capability_id: str
) -> tuple[Path, Path, Path, Path, Path, Path, Path]:
    return prior._runtime_paths(root=root, runtime_root=runtime_root, capability_id=capability_id)


def _context_proof(source_commit: str) -> str:
    return hashlib.sha256(f"{source_commit}:C13:SubagentStart".encode("utf-8")).hexdigest()[:32]


def _c13_hook_proxy_source() -> str:
    return r'''from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

raw = sys.stdin.read()
try:
    event = json.loads(raw) if raw.strip() else {}
except json.JSONDecodeError:
    event = {}
root = Path(subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"], text=True
).strip())
script = root / ".codex" / "hooks" / "subagent-start-fixture.py"
completed = subprocess.run(
    [sys.executable, str(script)],
    input=raw,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=False,
)
record = {
    "event": "SubagentStart",
    "returncode": completed.returncode,
}
try:
    parsed = json.loads(completed.stdout) if completed.stdout.strip() else {}
except json.JSONDecodeError:
    parsed = {}
if isinstance(parsed, dict):
    if "continue" in parsed:
        record["continue"] = parsed.get("continue")
    output = parsed.get("hookSpecificOutput")
    if isinstance(output, dict):
        record["additional_context"] = bool(output.get("additionalContext"))
log = root / ".pursue" / "qualification-c13-events.jsonl"
log.parent.mkdir(parents=True, exist_ok=True)
with log.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
sys.stdout.write(completed.stdout)
sys.stderr.write(completed.stderr)
raise SystemExit(completed.returncode)
'''


def _seed_c13(repo: Path, context_proof: str) -> None:
    _write(
        repo / ".codex" / "config.toml",
        """[agents]\nenabled = true\nmax_concurrent_threads_per_session = 2\n""",
    )
    _write(
        repo / ".codex" / "agents" / "fixture-agent.toml",
        'name = "fixture_agent"\n'
        'description = "C13 qualification child for real SubagentStart context semantics."\n'
        'sandbox_mode = "read-only"\n'
        'developer_instructions = """\n'
        'Do not use tools. Inspect only your already-active startup/developer context.\n'
        f'If it contains a line beginning `{C13_CONTEXT_PREFIX}`, reply exactly\n'
        f'`{C13_ECHO_PREFIX}<value>` where <value> is the exact opaque value after the equals sign.\n'
        f'If no such line is present, reply exactly `{C13_MISSING}`. Never guess a value.\n'
        '"""\n',
    )
    _write(
        repo / ".codex" / "hooks" / "subagent-start-fixture.py",
        "from __future__ import annotations\n"
        "import json\n\n"
        "print(json.dumps({\n"
        '    "continue": False,\n'
        '    "stopReason": "C13 compatibility signal: continue=false must not block SubagentStart",\n'
        '    "hookSpecificOutput": {\n'
        '        "hookEventName": "SubagentStart",\n'
        f'        "additionalContext": "{C13_CONTEXT_PREFIX}{context_proof}",\n'
        "    },\n"
        "}, sort_keys=True))\n",
    )
    _write(
        repo / ".codex" / "hooks" / "qualification-c13-hook-proxy.py",
        _c13_hook_proxy_source(),
    )
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
                                    "command": 'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/qualification-c13-hook-proxy.py"',
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
    _write(repo / "README.md", "C13 deterministic SubagentStart qualification fixture.\n")
    gitignore = repo / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if C13_HOOK_LOG_RELATIVE not in existing:
        with gitignore.open("a", encoding="utf-8") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            handle.write(C13_HOOK_LOG_RELATIVE + "\n")


def _c13_prompt() -> str:
    return f"""Exercise the real C13 SubagentStart semantics.

Start exactly one configured `fixture_agent` using the real Codex subagent mechanism. Do not
simulate the child, do not execute hook scripts manually, and do not use shell, command, file-read,
or file-write tools in the root session. Wait for that child to finish.

The child is designed to return either `{C13_ECHO_PREFIX}<opaque-value>` when it receives the
SubagentStart additional context, or `{C13_MISSING}` when it does not. Copy the child's exact
single-line response into one minimal observation. Never invent or guess the opaque value.

Return capability_id C13 and trial `subagent_start_context_and_continue_false`. PASS only when the
real child actually starts and returns the context-echo form. If startup cannot be exercised, return
BLOCKED. If the real child starts but reports missing context, return FAIL.
"""


def _hook_log(repo: Path) -> Path:
    return repo / C13_HOOK_LOG_RELATIVE


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


def _known_parent_thread_failure(*values: str) -> bool:
    return any(KNOWN_PARENT_THREAD_FAILURE_RE.search(value or "") for value in values)


def _build_codex_args(
    *,
    repo: Path,
    schema: Path,
    output: Path,
    ephemeral: bool,
    isolated_codex_home: Path | None = None,
) -> list[str]:
    args = base.common_codex_args(
        cwd=repo,
        sandbox="read-only",
        schema=schema,
        output=output,
        trust_project=True,
        hook_trust=True,
        ignore_rules=False,
    )
    if not ephemeral:
        try:
            args.remove("--ephemeral")
        except ValueError as exc:
            raise base.QualificationError("C13 runner could not remove the default ephemeral flag") from exc
        if isolated_codex_home is None:
            raise base.QualificationError("C13 non-ephemeral execution requires an isolated CODEX_HOME")
        sqlite_home = isolated_codex_home / "sqlite"
        log_dir = isolated_codex_home / "log"
        args += ["-c", 'history.persistence="none"']
        args += ["-c", f"sqlite_home={base.toml_quote(str(sqlite_home.resolve()))}"]
        args += ["-c", f"log_dir={base.toml_quote(str(log_dir.resolve()))}"]
    args.append(_c13_prompt())
    return args


def _run_c13_codex(
    *,
    repo: Path,
    schemas: dict[str, Path],
    results_dir: Path,
    position: int,
    ephemeral: bool,
    isolated_codex_home: Path | None = None,
    timeout: int = 600,
) -> tuple[dict[str, Any], dict[str, Any], str | None, bool]:
    suffix = "ephemeral" if ephemeral else "non-ephemeral"
    output = results_dir / f"trial-{position:02d}-{suffix}.json"
    output.unlink(missing_ok=True)
    args = _build_codex_args(
        repo=repo,
        schema=schemas["trial"],
        output=output,
        ephemeral=ephemeral,
        isolated_codex_home=isolated_codex_home,
    )
    env = os.environ.copy()
    if isolated_codex_home is not None:
        env["CODEX_HOME"] = str(isolated_codex_home)
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
        return {}, {"timeout": True}, "Codex invocation timed out", False

    events = base.event_summary(completed.stdout)
    payload: dict[str, Any] = {}
    parse_error: str | None = None
    if output.is_file():
        try:
            value = base.load_json(output)
            if isinstance(value, dict):
                payload = value
            else:
                parse_error = "Codex structured output was not a JSON object"
        except (OSError, json.JSONDecodeError) as exc:
            parse_error = f"Codex produced invalid structured output: {exc}"
    elif completed.returncode == 0:
        parse_error = "Codex did not produce the structured output file"

    serialized_payload = json.dumps(payload, sort_keys=True)
    known_failure = _known_parent_thread_failure(
        completed.stderr,
        completed.stdout,
        serialized_payload,
    )
    if completed.returncode != 0:
        error = f"Codex exited {completed.returncode}: {base.sanitize_text(completed.stderr[-2500:])}"
    else:
        error = parse_error
    return payload, events, error, known_failure


def _original_codex_home() -> Path:
    raw = os.environ.get("CODEX_HOME")
    return Path(raw).expanduser().resolve() if raw else (Path.home() / ".codex").resolve()


def _stat_fingerprint(path: Path) -> tuple[int, int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_size, stat.st_mtime_ns, stat.st_ino


def _prepare_isolated_codex_home(cap_runtime: Path) -> tuple[Path, Path | None, tuple[int, int, int] | None]:
    home = cap_runtime / "non-ephemeral-codex-home"
    shutil.rmtree(home, ignore_errors=True)
    home.mkdir(parents=True, mode=0o700)
    original_auth = _original_codex_home() / "auth.json"
    if not original_auth.is_file():
        return home, None, None
    fingerprint = _stat_fingerprint(original_auth)
    os.symlink(str(original_auth), str(home / "auth.json"))
    return home, original_auth, fingerprint


def _session_rollout_count(home: Path) -> int:
    sessions = home / "sessions"
    if not sessions.is_dir():
        return 0
    return sum(1 for path in sessions.rglob("*.jsonl") if path.is_file())


def _cleanup_isolated_codex_home(
    home: Path,
    auth_path: Path | None,
    auth_before: tuple[int, int, int] | None,
) -> tuple[bool, bool]:
    auth_unchanged = True
    if auth_path is not None:
        auth_unchanged = _stat_fingerprint(auth_path) == auth_before
    shutil.rmtree(home, ignore_errors=True)
    return not home.exists(), auth_unchanged


def _repo_unchanged(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return before == after


def _evaluate_transport(
    *,
    transport: str,
    payload: dict[str, Any],
    events: dict[str, Any],
    error: str | None,
    known_parent_failure: bool,
    records: list[dict[str, Any]],
    context_proof: str,
    git_before: dict[str, Any],
    git_after: dict[str, Any],
    session_rollouts_created: int = 0,
    session_cleanup_verified: bool = True,
    auth_unchanged: bool = True,
) -> tuple[str, dict[str, Any]]:
    serialized = json.dumps(payload, sort_keys=True)
    echo_observed = f"{C13_ECHO_PREFIX}{context_proof}" in serialized
    missing_observed = C13_MISSING in serialized
    subagent_records = [item for item in records if item.get("event") == "SubagentStart"]
    hook_exactly_once = len(subagent_records) == 1
    hook_continue_false = hook_exactly_once and subagent_records[0].get("continue") is False
    hook_additional_context = hook_exactly_once and subagent_records[0].get("additional_context") is True
    hook_ok = hook_exactly_once and hook_continue_false and hook_additional_context
    command_items = int(events.get("completed_command_items") or 0)
    file_change_items = int(events.get("completed_file_change_items") or 0)
    item_types = events.get("item_types") if isinstance(events.get("item_types"), dict) else {}
    error_items = int(item_types.get("error") or 0)
    unchanged = _repo_unchanged(git_before, git_after)
    isolated_persistence_ok = (
        transport == "ephemeral"
        or (session_rollouts_created > 0 and session_cleanup_verified and auth_unchanged)
    )

    if known_parent_failure and not hook_exactly_once:
        outcome = "BLOCKED"
        blocker = "recognized ephemeral parent-thread registration failure"
    elif error and not hook_exactly_once:
        outcome = "BLOCKED"
        blocker = error
    elif command_items or file_change_items:
        outcome = "BLOCKED"
        blocker = "root C13 probe used forbidden command/file tools"
    elif not unchanged:
        outcome = "FAILED"
        blocker = "C13 probe changed repository state"
    elif not hook_exactly_once:
        outcome = "BLOCKED"
        blocker = "exactly one real SubagentStart hook event was not observed"
    elif not hook_ok:
        outcome = "FAILED"
        blocker = "SubagentStart hook did not expose both additionalContext and continue=false as configured"
    elif not isolated_persistence_ok:
        outcome = "BLOCKED"
        blocker = "controlled non-ephemeral persistence/cleanup invariants were not verified"
    elif echo_observed and not missing_observed:
        outcome = "PASS"
        blocker = None
    else:
        outcome = "FAILED"
        blocker = "real child startup reached SubagentStart but the expected injected-context echo was not observed"

    trial = {
        "capability_id": "C13",
        "trial": "subagent_start_context_and_continue_false",
        "trial_name": "subagent_start_context_and_continue_false",
        "transport": transport,
        "outcome": outcome,
        "assertions": [
            {
                "name": "real_subagent_start_hook_executes_once",
                "status": "PASS" if hook_exactly_once else "BLOCKED",
                "evidence": f"subagent_start_hook_events={len(subagent_records)}",
            },
            {
                "name": "SubagentStart_can_add_context_for_the_starting_agent",
                "status": "PASS" if echo_observed and hook_additional_context else ("BLOCKED" if not hook_exactly_once else "FAIL"),
                "evidence": (
                    f"hook_additional_context={str(hook_additional_context).lower()}; "
                    f"child_context_echo_observed={str(echo_observed).lower()}"
                ),
            },
            {
                "name": "continue_false_does_not_become_a_relied_upon_startup_blocker",
                "status": "PASS" if echo_observed and hook_continue_false else ("BLOCKED" if not hook_exactly_once else "FAIL"),
                "evidence": (
                    f"hook_continue_false={str(hook_continue_false).lower()}; "
                    f"child_started_with_context={str(echo_observed).lower()}"
                ),
            },
        ],
        "observations": [
            f"known_parent_thread_failure={str(known_parent_failure).lower()}",
            f"subagent_start_hook_events={len(subagent_records)}",
            f"hook_continue_false={str(hook_continue_false).lower()}",
            f"hook_additional_context={str(hook_additional_context).lower()}",
            f"child_context_echo_observed={str(echo_observed).lower()}",
            f"child_missing_context_observed={str(missing_observed).lower()}",
            f"completed_command_items={command_items}",
            f"completed_file_change_items={file_change_items}",
            f"error_items={error_items}",
            f"repository_unchanged={str(unchanged).lower()}",
            f"session_rollouts_created={session_rollouts_created}",
            f"session_cleanup_verified={str(session_cleanup_verified).lower()}",
            f"auth_metadata_unchanged={str(auth_unchanged).lower()}",
        ],
        "blocker": blocker,
        "event_summary": events,
        "git_before": git_before,
        "git_after": git_after,
        "outer_hook_contract": {
            "project_scoped_hooks": True,
            "matcher": "^fixture_agent$",
            "additional_context_present": True,
            "returns_continue_false": True,
            "secret_value_retained_in_evidence": False,
        },
    }
    return outcome, base.sanitize(trial)


def _c13_runtime(
    *,
    root: Path,
    runtime_root: Path,
    schemas: dict[str, Path],
    version: str,
    os_name: str,
    source_commit: str,
    date: str,
) -> tuple[str, bool]:
    capability_id = "C13"
    cap_dir, cap_runtime, spec_dir, repo, worktrees, results_dir, evaluator_dir = _runtime_paths(
        root=root, runtime_root=runtime_root, capability_id=capability_id
    )
    del cap_dir, spec_dir, worktrees, evaluator_dir

    with prior.v2._python_bytecode_disabled():
        base.ensure_git_repo(repo)
        proof = _context_proof(source_commit)
        _seed_c13(repo, proof)
        fixture_commit = base.commit_fixture_baseline(repo)

        _clear_hook_log(repo)
        before_ephemeral = base.git_snapshot(repo)
        payload_e, events_e, error_e, known_e = _run_c13_codex(
            repo=repo,
            schemas=schemas,
            results_dir=results_dir,
            position=1,
            ephemeral=True,
            timeout=600,
        )
        after_ephemeral = base.git_snapshot(repo)
        records_e = _read_hook_records(repo)
        outcome_e, trial_e = _evaluate_transport(
            transport="ephemeral",
            payload=payload_e,
            events=events_e,
            error=error_e,
            known_parent_failure=known_e,
            records=records_e,
            context_proof=proof,
            git_before=before_ephemeral,
            git_after=after_ephemeral,
        )

        trials = [trial_e]
        fallback_used = False
        fallback_available = False
        cleanup_verified = True
        auth_unchanged = True

        if outcome_e == "PASS":
            final_outcome = "PASS"
            transport_resolution = "ephemeral"
        elif outcome_e == "FAILED":
            final_outcome = "FAILED"
            transport_resolution = "ephemeral_semantic_failure"
        elif not (known_e and ALLOW_NON_EPHEMERAL_FALLBACK):
            final_outcome = "BLOCKED"
            transport_resolution = (
                "ephemeral_known_transport_blocker_fallback_not_enabled"
                if known_e
                else "ephemeral_unclassified_blocker"
            )
        else:
            fallback_used = True
            isolated_home, auth_path, auth_before = _prepare_isolated_codex_home(cap_runtime)
            fallback_available = auth_path is not None
            if auth_path is None:
                shutil.rmtree(isolated_home, ignore_errors=True)
                cleanup_verified = not isolated_home.exists()
                final_outcome = "BLOCKED"
                transport_resolution = "isolated_non_ephemeral_auth_bridge_unavailable"
                trials.append(
                    {
                        "capability_id": capability_id,
                        "trial": "non_ephemeral_fallback_preflight",
                        "trial_name": "non_ephemeral_fallback_preflight",
                        "transport": "non-ephemeral",
                        "outcome": "BLOCKED",
                        "assertions": [],
                        "observations": [
                            "authenticated CODEX_HOME did not expose a file-backed auth.json for a no-copy symlink bridge",
                            f"session_cleanup_verified={str(cleanup_verified).lower()}",
                        ],
                        "blocker": "isolated non-ephemeral auth bridge unavailable",
                    }
                )
            else:
                _clear_hook_log(repo)
                before_fallback = base.git_snapshot(repo)
                try:
                    payload_n, events_n, error_n, known_n = _run_c13_codex(
                        repo=repo,
                        schemas=schemas,
                        results_dir=results_dir,
                        position=2,
                        ephemeral=False,
                        isolated_codex_home=isolated_home,
                        timeout=600,
                    )
                    session_rollouts = _session_rollout_count(isolated_home)
                    after_fallback = base.git_snapshot(repo)
                    records_n = _read_hook_records(repo)
                finally:
                    cleanup_verified, auth_unchanged = _cleanup_isolated_codex_home(
                        isolated_home,
                        auth_path,
                        auth_before,
                    )
                outcome_n, trial_n = _evaluate_transport(
                    transport="non-ephemeral",
                    payload=payload_n,
                    events=events_n,
                    error=error_n,
                    known_parent_failure=known_n,
                    records=records_n,
                    context_proof=proof,
                    git_before=before_fallback,
                    git_after=after_fallback,
                    session_rollouts_created=session_rollouts,
                    session_cleanup_verified=cleanup_verified,
                    auth_unchanged=auth_unchanged,
                )
                trials.append(trial_n)
                final_outcome = outcome_n
                transport_resolution = "non_ephemeral_fallback"

    if final_outcome == "PASS":
        result = "REPRODUCED"
        expected_met = True
        blocker = None
        if transport_resolution == "ephemeral":
            summary = "C13 reproduced directly under ephemeral execution with one real SubagentStart hook and child context echo."
        else:
            summary = "C13 diagnostic reproduced the documented SubagentStart semantics through the controlled non-ephemeral fallback after the recognized ephemeral parent-thread registration failure."
    elif final_outcome == "FAILED":
        result = "FAILED"
        expected_met = False
        blocker = "C13 reached real SubagentStart startup but observed semantics contradicted the expected context/continue=false contract."
        summary = "C13 failed after reaching the real SubagentStart semantic boundary."
    else:
        result = "BLOCKED"
        expected_met = False
        blocker = "C13 could not reach and verify the real child startup semantics under the permitted qualification transport."
        summary = "C13 remains blocked because the real SubagentStart semantic boundary was not completely exercised."

    return prior._write_result(
        root=root,
        cap_runtime=cap_runtime,
        capability_id=capability_id,
        result=result,
        expected_met=expected_met,
        observations=[
            f"ephemeral_outcome={outcome_e}",
            f"ephemeral_known_parent_thread_failure={str(known_e).lower()}",
            f"non_ephemeral_fallback_enabled={str(ALLOW_NON_EPHEMERAL_FALLBACK).lower()}",
            f"non_ephemeral_fallback_used={str(fallback_used).lower()}",
            f"non_ephemeral_fallback_available={str(fallback_available).lower()}",
            f"session_cleanup_verified={str(cleanup_verified).lower()}",
            f"auth_metadata_unchanged={str(auth_unchanged).lower()}",
            f"transport_resolution={transport_resolution}",
        ],
        blocker=blocker,
        summary=summary,
        trials=trials,
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
    return _c13_runtime(**common)


def _prepare_controller_root(root: Path, source_commit: str) -> None:
    if not (root / ".git").exists():
        raise base.QualificationError(f"qualification root is not a Git repository: {root}")
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise base.QualificationError("--source-commit must be a full Git SHA")
    if base.git(root, "rev-parse", "HEAD") != source_commit:
        raise base.QualificationError("qualification repository HEAD does not match --source-commit")
    base.run([sys.executable, "tools/validate_capabilities.py"], cwd=root, timeout=120)
    base.git(root, "config", "user.name", "PlanAnvil Qualification")
    base.git(root, "config", "user.email", "plananvil-qualification@example.invalid")
    base.git(root, "config", "commit.gpgsign", "false")
    base.git(root, "config", "protocol.file.allow", "always")
    base.git(root, "add", "capabilities")
    base.run(
        ["git", "commit", "--allow-empty", "-q", "-m", "Materialize capability qualification templates"],
        cwd=root,
        timeout=60,
    )


def _c13_only_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run PlanAnvil C13 transport diagnostic")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--only", choices=["C13"], required=True)
    args = parser.parse_args(argv)

    root = args.root.resolve()
    _prepare_controller_root(root, args.source_commit)
    version = base.codex_version()
    os_name = base.os_label()
    date = dt.date.today().isoformat()

    runtime_root = root / ".qualification-runtime"
    shutil.rmtree(runtime_root, ignore_errors=True)
    runtime_root.mkdir()
    exclude = root / ".git" / "info" / "exclude"
    with exclude.open("a", encoding="utf-8") as handle:
        handle.write("\n.qualification-runtime/\n")
    schemas = base.write_schemas(runtime_root / "schemas")

    try:
        print("=== C13: transport diagnostic ===", flush=True)
        try:
            result, required = capability_runtime(
                root=root,
                runtime_root=runtime_root,
                capability_id="C13",
                schemas=schemas,
                version=version,
                os_name=os_name,
                source_commit=args.source_commit,
                date=date,
            )
        except Exception as exc:
            blocker = base.sanitize_text(f"{type(exc).__name__}: {exc}")
            required = True
            base.write_evidence(
                root=root,
                capability_id="C13",
                result="BLOCKED",
                expected_met=False,
                observations=["C13 diagnostic controller blocked before completing the transport comparison."],
                blocker=blocker,
                summary="C13 blocked by diagnostic controller error.",
                trials=[],
                fixture_commit=None,
                version=version,
                os_name=os_name,
                source_commit=args.source_commit,
                date=date,
            )
            base.local_commit(root, "C13")
            result = "BLOCKED"

        summary = {
            "schema_version": "1.0",
            "date": date,
            "source_commit": args.source_commit,
            "github_actions_run": args.run_id,
            "codex_version": version,
            "model": base.MODEL,
            "os": os_name,
            "scope": ["C13"],
            "diagnostic_only": True,
            "result": result,
            "required": required,
            "c13_semantics_reproduced": result == "REPRODUCED",
        }
        base.stage_artifact(root, args.output.resolve(), summary)
        print(f"C13: {result}", flush=True)
        print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
        return 0 if result == "REPRODUCED" else 2
    finally:
        shutil.rmtree(runtime_root, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    global ALLOW_NON_EPHEMERAL_FALLBACK
    args = list(sys.argv[1:] if argv is None else argv)
    allow_flag = "--allow-c13-non-ephemeral-fallback"
    ALLOW_NON_EPHEMERAL_FALLBACK = allow_flag in args
    args = [item for item in args if item != allow_flag]
    base.capability_runtime = capability_runtime
    if ALLOW_NON_EPHEMERAL_FALLBACK and "--only" not in args:
        raise base.QualificationError(
            "C13 non-ephemeral fallback is diagnostic-only until the baseline contract is updated"
        )
    if "--only" in args:
        if not ALLOW_NON_EPHEMERAL_FALLBACK:
            raise base.QualificationError(
                "C13-only diagnostic requires --allow-c13-non-ephemeral-fallback"
            )
        return _c13_only_main(args)
    return base.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
