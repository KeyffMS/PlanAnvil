"""Finite C09 workload: real read-only recovery, two large outputs, then finish.

This module prepares the disposable fixture, not product behavior. It never
invokes lifecycle hooks or supplies fabricated live events to the evaluator.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

COMPACT_LIMIT = 8192
OUTPUT_TOKENS = 65536
PHASES = ("first", "second", "finish")
SCRIPT = "qualification-payload/c09_probe.py"
TRIAL = "checkpoint_auto_compact_recover_recompact"
COMMANDS = {phase: f"python3 -B {SCRIPT} {phase}" for phase in PHASES}

# Shipped only in a disposable qualification repository. All runtime operations
# are reads. Checkpoint/Git decisions come from the installed product validator.
PROBE_SOURCE = r'''from __future__ import annotations
import hashlib, json, sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / ".codex" / "hooks"))
from plan_anvil_hooklib import active_run_for_event
from plan_anvil_checkpoint import validate_checkpoint_for_run

def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"first", "second", "finish"}:
        return 2
    phase = sys.argv[1]
    active = active_run_for_event({"cwd": str(root)})
    if active is None:
        return 2
    check = validate_checkpoint_for_run(active)
    if not check.ok or check.path is None:
        print(json.dumps({"c09_phase": phase, "checkpoint_ok": False}))
        return 2
    files = [active.run_root / "manifest.json", active.run_root / "state.json",
             active.run_root / "local-state.json", check.path]
    files += sorted((root / ".pursue").glob("SYSTEM_PROFILE*.md"))
    # Fully read the canonical recovery inputs without printing local-state or
    # paths. The real validator above reconciles canonical identity with Git.
    sizes = [len(path.read_bytes()) for path in files]
    state = json.loads((active.run_root / "state.json").read_text(encoding="utf-8"))
    if state.get("next_action") != {"type": "C09_FINITE_RECOVERY", "target": "evidence/c09-scenario.json"}:
        return 2
    scenario = json.loads((active.run_root / "evidence/c09-scenario.json").read_text(encoding="utf-8"))
    if scenario.get("phases") != ["first", "second", "finish"]:
        return 2
    receipt = {"c09_phase": phase, "checkpoint_ok": True, "canonical_read": True,
               "git_reconciled": True, "canonical_file_count": len(files),
               "canonical_bytes": sum(sizes)}
    print(json.dumps(receipt, sort_keys=True))
    if phase != "finish":
        # Deterministic inert high-volume output, not an instruction or a secret.
        # A phase-specific stimulus avoids eight indistinguishable repeated reads.
        for i in range(1024):
            print(hashlib.sha512((phase + ":" + str(i)).encode()).hexdigest())
    print(json.dumps(receipt, sort_keys=True))
    print("C09_NEXT=" + {"first": "second", "second": "finish", "finish": "RETURN_RESULT"}[phase])
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError):
        # No raw canonical contents/private paths in errors or evidence.
        print("C09_FIXTURE_READ_FAILED", file=sys.stderr)
        raise SystemExit(2)
'''


def prepare_repo(repo: Path) -> None:
    path = repo / SCRIPT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PROBE_SOURCE, encoding="utf-8")


def seed_state(planning: Path, run_root: str) -> None:
    """Replace bootstrap's unrelated MAP_INSTRUCTIONS action before checkpointing."""
    run = planning / run_root
    scenario = {"schema_version": "1.0", "phases": list(PHASES), "commands": COMMANDS,
                "completion": "Return the final C09 result after finish; never restart first."}
    data = (json.dumps(scenario, indent=2, sort_keys=True) + "\n").encode()
    path = run / "evidence/c09-scenario.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    state_path = run / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["revision"] += 1
    state["next_action"] = {"type": "C09_FINITE_RECOVERY", "target": "evidence/c09-scenario.json"}
    state.setdefault("artifact_hashes", {})["evidence/c09-scenario.json"] = "sha256:" + hashlib.sha256(data).hexdigest()
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def prompt() -> str:
    return f'''Qualify C09 using this finite, read-only scenario in ONE Codex turn.
The outer harness has already installed PlanAnvil and created a valid checkpoint.
Do not start a plan, map instructions, or create/repair any files. The canonical
next action is C09_FINITE_RECOVERY, not the earlier bootstrap MAP_INSTRUCTIONS.

Make exactly THREE sequential exec_command calls, each once and in this order:
1. cmd={COMMANDS["first"]!r}, max_output_tokens={OUTPUT_TOKENS}
2. cmd={COMMANDS["second"]!r}, max_output_tokens={OUTPUT_TOKENS}
3. cmd={COMMANDS["finish"]!r}, max_output_tokens=2048
Use workdir for the current planning directory; do not prepend cd or combine calls.
Wait for each command to finish before choosing the next one. The first two outputs
are inert compaction stimuli: do not analyse, quote, hash, or reread their padding.

After each automatic compaction continue with the NEXT phase, never restart first.
Each command fully reads manifest/state/local-state/checkpoint/profiles and calls the
actual product checkpoint/Git validator. This performs the recovery requested by the
SessionStart context; do not perform additional recovery reads outside those commands.
No manual hook calls, telemetry reads, other tools, state changes, or subagents.

After finish exits 0, make NO further calls. Return capability_id C09, trial {TRIAL},
outcome PASS, and observation C09_FINISHED. If a command fails, stop with FAIL/BLOCKED;
do not retry. The outer evaluator, not your self-report, checks the real compactions.
'''


def proxy_source(original: str) -> str:
    """Extend only C09 telemetry without changing stdout or any product decision."""
    addition = '''\nif isinstance(event, dict):
    source = event.get("source")
    if source in {"startup", "resume", "clear", "compact"}:
        record["source"] = source
    trigger = event.get("trigger")
    if trigger in {"auto", "manual"}:
        record["trigger"] = trigger
    raw_command = event.get("tool_input", {}).get("command") if isinstance(event.get("tool_input"), dict) else None
    commands = ''' + repr({command: phase for phase, command in COMMANDS.items()}) + '''
    if event_name == "PreToolUse":
        record["c09_phase"] = commands.get(raw_command, "other")
'''
    anchor = 'try:\n    parsed = json.loads(completed.stdout)'
    # The active compat adapter has this exact executable contract, covered by
    # subprocess tests. Reject a future adapter change instead of silently losing evidence.
    if anchor not in original:
        raise ValueError("C09 telemetry adapter contract changed")
    return original.replace(anchor, addition + "\n" + anchor, 1)


def file_fingerprint(repo: Path) -> str:
    """Hash all fixture files, including ignored canonical state, without paths in evidence.

    Git status alone misses edits to an already-untracked state file. Exclude only
    Git's database/locator and the known legacy telemetry sink (normally external).
    """
    if not repo.is_dir():
        raise ValueError("C09 fixture directory is missing")
    digest = hashlib.sha256()
    def walk_error(_error: OSError) -> None:
        raise ValueError("C09 fixture files could not be completely inspected")

    for directory, dirs, names in os.walk(repo, onerror=walk_error):
        for name in dirs:
            if name != ".git" and (Path(directory) / name).is_symlink():
                raise ValueError("Unexpected directory symlink in C09 fixture")
        dirs[:] = sorted(d for d in dirs if d != ".git")
        for name in sorted(names):
            path = Path(directory) / name
            rel = path.relative_to(repo).as_posix()
            if rel in {".git", ".pursue/qualification-hook-events.jsonl"}:
                continue
            if path.is_symlink():
                raise ValueError("Unexpected symlink in C09 fixture")
            data = path.read_bytes()
            digest.update(rel.encode("utf-8") + b"\0")
            digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


def protocol_checks(events: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, bool]:
    commands = [r for r in events.get("event_tail", [])
                if r.get("event") == "item.completed" and r.get("item") == "command_execution"]
    expected = ["c09_" + phase for phase in PHASES]
    command_order = ([r.get("command") for r in commands] == expected
                     and all(r.get("exit_code") == 0 and r.get("c09_receipt_ok") is True for r in commands)
                     and events.get("completed_command_items") == 3
                     and not events.get("event_tail_truncated"))
    tool_rows = [r for r in records if r.get("event") == "PreToolUse"]
    hook_order = [r.get("c09_phase") for r in tool_rows] == list(PHASES)
    positions = {r.get("c09_phase"): i for i, r in enumerate(records) if r.get("event") == "PreToolUse"}
    cycles = hook_order
    for start, end in (("first", "second"), ("second", "finish")):
        between = records[positions[start] + 1:positions[end]] if hook_order else []
        lifecycle = [r.get("event") for r in between if r.get("event") in {"PreCompact", "PostCompact", "SessionStart"}]
        cycles = cycles and lifecycle == ["PreCompact", "PostCompact", "SessionStart"]
        cycles = cycles and all(r.get("trigger") == "auto" for r in between if r.get("event") in {"PreCompact", "PostCompact"})
        cycles = cycles and any(r.get("event") == "SessionStart" and r.get("source") == "compact"
                                and r.get("additional_context") is True for r in between)
    hooks_ok = bool(records) and all(r.get("returncode") == 0 for r in records)
    forbidden = sum(events.get("item_types", {}).get(k, 0) for k in
                    ("file_change", "mcp_tool_call", "web_search", "collab_tool_call", "other"))
    return {"three_completed_reconciliations": command_order,
            "ordered_automatic_recovery_cycles": bool(cycles), "product_hooks_succeeded": hooks_ok,
            "no_unexpected_tools": not forbidden,
            "turn_completed": events.get("event_types", {}).get("turn.completed") == 1
                              and not events.get("event_types", {}).get("turn.failed")}
