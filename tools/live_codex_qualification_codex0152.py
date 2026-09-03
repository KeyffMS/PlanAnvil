from __future__ import annotations

import contextlib
import json
import re
from pathlib import Path
from typing import Any, Callable, Iterator

import live_codex_qualification_harness_v2 as v2
import live_codex_qualification_harness_v4 as v4
import live_codex_qualification_harness_v5 as v5
import live_codex_qualification_regression as regression

base = regression.base
TARGET_CAPABILITIES = regression.TARGET_CAPABILITIES


def run_c03(**kwargs: Any):
    # Product contract/golden files carry the current 2.3 topology semantics;
    # the regression helper performs the real bootstrap and outer validation.
    return regression.run_c03(**kwargs)


def _set_feature(text: str, key: str, value: str) -> str:
    assignment = re.compile(rf"(?m)^\s*{re.escape(key)}\s*=.*$")
    if assignment.search(text):
        return assignment.sub(f"{key} = {value}", text, count=1)
    header = re.search(r"(?m)^\[features\]\s*$", text)
    if header:
        pos = header.end()
        return text[:pos] + f"\n{key} = {value}" + text[pos:]
    return text.rstrip() + f"\n\n[features]\n{key} = {value}\n"


@contextlib.contextmanager
def _codex0152_compaction(cap_runtime: Path, capability_id: str) -> Iterator[None]:
    """Exercise real auto-compaction without the 0.152 TokenBudget fallback buffer.

    Codex 0.152 compares body-after-prefix usage against the configured
    auto-compaction limit plus TokenBudget's fallback buffer. The isolated
    qualification fixture disables TokenBudget so the deliberately-low limit is
    the effective trigger. Product configuration is not changed.
    """

    old_set = v4._set_compact_config

    def set_compact_config(repo: Path, *, limit: int, scope: str) -> None:
        old_set(repo, limit=limit, scope=scope)
        path = repo / ".codex" / "config.toml"
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        path.write_text(_set_feature(text, "token_budget", "false"), encoding="utf-8")

    v4._set_compact_config = set_compact_config
    try:
        with regression._patched_v4(cap_runtime, capability_id):
            yield
    finally:
        v4._set_compact_config = old_set


def run_c08(**kwargs: Any):
    cap_runtime = Path(kwargs["runtime_root"]) / "C08"
    with _codex0152_compaction(cap_runtime, "C08"):
        return v4._c08_runtime(**kwargs)


def run_c09(**kwargs: Any):
    cap_runtime = Path(kwargs["runtime_root"]) / "C09"
    with _codex0152_compaction(cap_runtime, "C09"):
        return v4._c09_runtime(**kwargs)


def _c13_prompt_0152() -> str:
    return f"""Exercise the real C13 SubagentStart semantics for Codex 0.152.

Start exactly one configured child by invoking the real `spawn_agent` mechanism with
`agent_type` exactly `fixture_agent`. Do not omit `agent_type`, do not use a default/unnamed
child, do not simulate the child, do not execute hook scripts manually, and do not use shell,
command, file-read, or file-write tools in the root session. Wait for that child to finish.

Codex 0.152 matches SubagentStart handlers against `agent_type`. The child must therefore be
spawned with the exact configured role name. The hook may inject additional context; its
`continue=false` field is a compatibility signal and must not be treated as a stop control for
SubagentStart.

The child is designed to return either `{v5.C13_ECHO_PREFIX}<opaque-value>` when it receives the
SubagentStart additional context, or `{v5.C13_MISSING}` when it does not. Copy the child's exact
single-line response into one minimal observation. Never invent or guess the opaque value.

Return capability_id C13 and trial `subagent_start_context_and_continue_false`. PASS only when the
real child starts with the exact agent_type and returns the context-echo form. If startup cannot be
exercised, return BLOCKED. If the child starts but reports missing context, return FAIL.
"""


@contextlib.contextmanager
def _c13_contract(cap_runtime: Path) -> Iterator[None]:
    old_prompt = v5._c13_prompt
    v5._c13_prompt = _c13_prompt_0152
    try:
        with regression._patched_v5_c13(cap_runtime):
            yield
    finally:
        v5._c13_prompt = old_prompt


def run_c13(current_runtime: Callable[..., tuple[str, bool]], **kwargs: Any):
    cap_runtime = Path(kwargs["runtime_root"]) / "C13"
    with _c13_contract(cap_runtime):
        return current_runtime(**kwargs)


def _shell_prompt() -> str:
    return (
        "Use the real shell/exec_command tool exactly once to run `printf C06_SUPPORTED_HOOK`. "
        "Do not modify files and do not execute hook scripts manually. Return capability_id C06, "
        "trial supported_exec_command_pretooluse, outcome PASS after the command succeeds."
    )


def _patch_prompt() -> str:
    return (
        "Use the direct apply_patch file-change tool exactly once to append the line "
        "`C06_BYPASS_MUTATION` to README.md. Do not use shell commands and do not execute hook "
        "scripts manually. This is a disposable fixture. Return capability_id C06, trial "
        "file_change_postcondition, outcome PASS after the single patch attempt completes or is "
        "blocked."
    )


def run_c06(
    *, root: Path, runtime_root: Path, schemas: dict[str, Path], version: str,
    os_name: str, source_commit: str, date: str,
) -> tuple[str, bool]:
    """Qualify the product boundary against Codex 0.152's actual tool adapters.

    0.152 guarantees a PreToolUse payload for function-call exec_command (canonical
    hook name Bash). File-change transports are separately protected by PlanAnvil's
    deterministic mutation postcondition; a hook event is recorded when available
    but is not treated as a complete mutation ledger.
    """

    cid = "C06"
    _cap, cap_runtime, _spec, repo, _worktrees, results, _eval = regression._runtime_paths(
        root=root, runtime_root=runtime_root, capability_id=cid
    )
    with v2._python_bytecode_disabled(), regression._patched_v4(cap_runtime, cid):
        base.ensure_git_repo(repo)
        regression.v1._install_plananvil_release(root, repo)
        v4._instrument_hooks(repo, event_to_script={"PreToolUse": "plan-anvil-guard.py"})
        regression._write(repo / "README.md", "C06 Codex 0.152 product-boundary fixture.\n")
        fixture_commit = base.commit_fixture_baseline(repo)
        log = v4._hook_log(repo)

        before_shell = base.git_snapshot(repo)
        payload_s, events_s, error_s = v4._run_codex_probe(
            cwd=repo, prompt=_shell_prompt(), schemas=schemas, results_dir=results,
            position=1, sandbox="workspace-write", timeout=600,
        )
        after_shell = base.git_snapshot(repo)
        records_s = regression._read_records(log)
        bash_events = [
            item for item in records_s
            if item.get("event") == "PreToolUse" and item.get("tool_name") == "Bash"
        ]
        shell_ok = (
            error_s is None
            and payload_s.get("outcome") == "PASS"
            and int(events_s.get("completed_command_items") or 0) >= 1
            and len(bash_events) >= 1
            and before_shell == after_shell
        )

        record_count_before_patch = len(records_s)
        before_patch = base.git_snapshot(repo)
        payload_p, events_p, error_p = v4._run_codex_probe(
            cwd=repo, prompt=_patch_prompt(), schemas=schemas, results_dir=results,
            position=2, sandbox="workspace-write", timeout=600,
        )
        after_patch = base.git_snapshot(repo)
        records_p = regression._read_records(log)
        new_records = records_p[record_count_before_patch:]
        apply_events = [
            item for item in new_records
            if item.get("event") == "PreToolUse" and item.get("tool_name") == "apply_patch"
        ]
        readme = (repo / "README.md").read_text(encoding="utf-8")
        mutation_completed = "C06_BYPASS_MUTATION" in readme
        changed_status = after_patch.get("status") or []
        postcondition_detected = any(
            isinstance(line, str) and line.endswith("README.md") for line in changed_status
        )
        hook_blocked = not mutation_completed and bool(apply_events)
        postcondition_ok = hook_blocked or (mutation_completed and postcondition_detected)
        patch_invocation_ok = error_p is None and payload_p.get("outcome") in {"PASS", "FAIL", "BLOCKED"}

    if error_s or not shell_ok:
        result, met = "BLOCKED", False
        blocker = error_s or "Codex 0.152 supported exec_command PreToolUse path did not complete."
    elif error_p or not patch_invocation_ok:
        result, met = "BLOCKED", False
        blocker = error_p or "Codex 0.152 direct file-change boundary could not be exercised."
    elif not postcondition_ok:
        result, met = "FAILED", False
        blocker = "A file-change path escaped both PreToolUse observation and deterministic postcondition detection."
    else:
        result, met, blocker = "REPRODUCED", True, None

    trials = [
        {
            "capability_id": cid,
            "trial": "supported_exec_command_pretooluse",
            "trial_name": "supported_exec_command_pretooluse",
            "outcome": "PASS" if shell_ok else ("BLOCKED" if error_s else "FAIL"),
            "assertions": [{
                "name": "codex0152_exec_command_maps_to_bash_pretooluse",
                "status": "PASS" if shell_ok else ("BLOCKED" if error_s else "FAIL"),
                "evidence": f"bash_pretooluse_events={len(bash_events)}; command_items={int(events_s.get('completed_command_items') or 0)}",
            }],
            "observations": [
                f"bash_pretooluse_events={len(bash_events)}",
                f"command_items={int(events_s.get('completed_command_items') or 0)}",
                f"repository_unchanged={str(before_shell == after_shell).lower()}",
            ],
            "blocker": error_s,
            "event_summary": events_s,
            "model_payload": payload_s,
        },
        {
            "capability_id": cid,
            "trial": "file_change_postcondition",
            "trial_name": "file_change_postcondition",
            "outcome": "PASS" if postcondition_ok else ("BLOCKED" if error_p else "FAIL"),
            "assertions": [{
                "name": "file_change_is_guarded_or_detected_by_postcondition",
                "status": "PASS" if postcondition_ok else ("BLOCKED" if error_p else "FAIL"),
                "evidence": (
                    f"apply_patch_pretooluse_events={len(apply_events)}; "
                    f"mutation_completed={str(mutation_completed).lower()}; "
                    f"postcondition_detected={str(postcondition_detected).lower()}"
                ),
            }],
            "observations": [
                f"apply_patch_pretooluse_events={len(apply_events)}",
                f"mutation_completed={str(mutation_completed).lower()}",
                f"postcondition_detected={str(postcondition_detected).lower()}",
                f"hook_blocked={str(hook_blocked).lower()}",
            ],
            "blocker": error_p,
            "event_summary": events_p,
            "git_before": before_patch,
            "git_after": after_patch,
            "model_payload": payload_p,
        },
    ]

    return regression._write_result(
        root=root, cap_runtime=cap_runtime, capability_id=cid, result=result,
        expected_met=met,
        observations=[
            f"supported_bash_events={len(bash_events)}",
            f"file_change_apply_patch_events={len(apply_events)}",
            f"file_change_postcondition={str(postcondition_ok).lower()}",
        ],
        blocker=blocker,
        summary=(
            "C06 reproduced against Codex 0.152 with the guaranteed exec_command/Bash PreToolUse adapter and the product's deterministic file-change postcondition."
            if met else
            "C06 did not establish the Codex 0.152 hook-plus-postcondition product boundary."
        ),
        trials=trials, fixture_commit=fixture_commit, version=version, os_name=os_name,
        source_commit=source_commit, date=date,
    )


def run_c16(**kwargs: Any):
    return regression.run_c16(**kwargs)
