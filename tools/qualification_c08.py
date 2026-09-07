"""Finite C08 stop/repair fixture and fail-closed observations (not product code)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from qualification_c09 import file_fingerprint

COMPACT_LIMIT = 8192
OUTPUT_TOKENS = 65536
PHASES = ("pressure", "finish")
SCRIPT = "qualification-payload/c08_probe.py"
COMMANDS = {phase: f"python3 -B {SCRIPT} {phase}" for phase in PHASES}
INVALID_TRIAL = "automatic_compaction_without_valid_checkpoint"
REPAIRED_TRIAL = "automatic_compaction_after_checkpoint_repair"
PROBE_SOURCE = r'''from __future__ import annotations
import hashlib, json, sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / ".codex/hooks"))
from plan_anvil_hooklib import active_run_for_event
from plan_anvil_checkpoint import validate_checkpoint_for_run

def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"pressure", "finish"}:
        return 2
    phase = sys.argv[1]
    active = active_run_for_event({"cwd": str(root)})
    if active is None:
        return 2
    state = json.loads((active.run_root / "state.json").read_text(encoding="utf-8"))
    if state.get("next_action") != {"type": "C08_FINITE_RECOVERY", "target": "evidence/c08-scenario.json"}:
        return 2
    check = validate_checkpoint_for_run(active)
    if phase == "finish" and not check.ok:
        return 2
    files = [active.run_root / n for n in ("manifest.json", "state.json", "local-state.json")]
    files += sorted((root / ".pursue").glob("SYSTEM_PROFILE*.md"))
    if check.ok and check.path is not None:
        files.append(check.path)
    for path in files:
        path.read_bytes()
    receipt = {"c08_phase": phase, "canonical_read": True,
               "checkpoint_ok": check.ok, "git_reconciled": check.ok}
    print(json.dumps(receipt, sort_keys=True))
    if phase == "pressure":
        for i in range(1024):
            print(hashlib.sha512(("c08:" + str(i)).encode()).hexdigest())
    print(json.dumps(receipt, sort_keys=True))
    print("C08_NEXT=" + ("finish" if phase == "pressure" else "RETURN_RESULT"))
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError):
        print("C08_FIXTURE_READ_FAILED", file=sys.stderr)
        raise SystemExit(2)
'''


def prepare_repo(repo: Path) -> None:
    path = repo / SCRIPT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PROBE_SOURCE, encoding="utf-8")
    # This fixture tests PreCompact, not startup recovery. Keep the real compact
    # recovery handler and configure its actual root source before bootstrap.
    path = repo / ".codex/hooks.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if not value.get("hooks", {}).get("SessionStart"):
        raise ValueError("C08 requires the product compact recovery hook")
    for group in value["hooks"]["SessionStart"]:
        group["matcher"] = "^compact$"
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def seed_state(planning: Path, run_root: str) -> None:
    run = planning / run_root
    target = "evidence/c08-scenario.json"
    scenario = {"phases": list(PHASES), "commands": COMMANDS,
                "completion": "Continue with finish after compaction; never repeat pressure."}
    data = (json.dumps(scenario, indent=2, sort_keys=True) + "\n").encode()
    (run / target).write_bytes(data)
    path = run / "state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["revision"] += 1
    state["next_action"] = {"type": "C08_FINITE_RECOVERY", "target": target}
    state.setdefault("artifact_hashes", {})[target] = "sha256:" + hashlib.sha256(data).hexdigest()
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def prompt(*, repaired: bool) -> str:
    trial = REPAIRED_TRIAL if repaired else INVALID_TRIAL
    preparation = ("A valid checkpoint was created by the outer harness."
                   if repaired else "The checkpoint is intentionally missing. Do not repair it: the real PreCompact hook is expected to stop this negative probe.")
    return f'''Qualify C08 in ONE finite read-only turn. {preparation}
This is a fixture probe, not a request to start a plan or map instructions.
Make exactly these TWO sequential exec_command calls, each once:
1. cmd={COMMANDS['pressure']!r}, max_output_tokens={OUTPUT_TOKENS}
2. cmd={COMMANDS['finish']!r}, max_output_tokens=2048
Use the current planning workdir. Do not prepend cd, combine commands or use other tools.
The first output is inert compaction pressure; do not analyse or reread the padding.
If PreCompact stops this turn, stop. Do not retry, repair state or invoke hooks manually.
Otherwise, after automatic compaction continue with finish, never repeat pressure.
Finish uses the real product checkpoint/Git validator and reads the canonical recovery files.
This performs the recovery requested by SessionStart(compact); no extra recovery reads.
After finish exits zero make NO more calls. Return capability_id C08, trial {trial},
outcome PASS, and observation C08_FINISHED. Any command failure means FAIL/BLOCKED, not retry.
Do not change any files, read telemetry, spawn agents or execute a generated plan.
'''


def proxy_source(original: str) -> str:
    anchor = 'try:\n    parsed = json.loads(completed.stdout)'
    if anchor not in original:
        raise ValueError("C08 telemetry adapter contract changed")
    addition = '''
if isinstance(event, dict):
    if event.get("source") in {"startup", "resume", "clear", "compact"}:
        record["source"] = event["source"]
    if event.get("trigger") in {"auto", "manual"}:
        record["trigger"] = event["trigger"]
    commands = ''' + repr({cmd: phase for phase, cmd in COMMANDS.items()}) + '''
    if event_name == "PreToolUse":
        raw = event.get("tool_input", {})
        record["c08_phase"] = commands.get(raw.get("command") if isinstance(raw, dict) else None, "other")
'''
    return original.replace(anchor, addition + "\n" + anchor, 1)


def protocol_checks(events: dict[str, Any], records: list[dict[str, Any]], *, repaired: bool) -> dict[str, bool]:
    phases = list(PHASES) if repaired else ["pressure"]
    commands = [r for r in events.get("event_tail", []) if r.get("event") == "item.completed"
                and r.get("item") == "command_execution"]
    tools = [r for r in records if r.get("event") == "PreToolUse"]
    ordered_tools = [r.get("c08_phase") for r in tools] == phases
    sequence = [r.get("event") for r in records if r.get("event") in
                {"PreToolUse", "PreCompact", "PostCompact", "SessionStart"}]
    expected = (["PreToolUse", "PreCompact", "PostCompact", "SessionStart", "PreToolUse"]
                if repaired else ["PreToolUse", "PreCompact"])
    pre = [r for r in records if r.get("event") == "PreCompact"]
    decision = (len(pre) == 1 and pre[0].get("continue") is not False if repaired else
                len(pre) == 1 and pre[0].get("continue") is False and
                bool(pre[0].get("stop_reason_mentions_checkpoint") or pre[0].get("stop_reason_mentions_recovery")))
    forbidden = sum(events.get("item_types", {}).get(k, 0) for k in
                    ("file_change", "mcp_tool_call", "web_search", "collab_tool_call", "other"))
    rc = events.get("process_returncode")
    return {
        "complete_process_observation": events.get("process_cleanup_ok") is True
            and type(rc) is int and (rc == 0 if repaired else rc == 1)
            and events.get("timeout") is False and not events.get("reader_failed")
            and not events.get("event_tail_truncated") and not events.get("invalid_json_lines")
            and not events.get("oversized_lines"),
        "exact_completed_commands": len(commands) == len(phases)
            and events.get("completed_command_items") == len(phases)
            and [r.get("command") for r in commands] == ["c08_" + p for p in phases]
            and all(r.get("exit_code") == 0 and r.get("c08_receipt_ok") is True
                    and r.get("c08_checkpoint_ok") is repaired for r in commands),
        "ordered_automatic_lifecycle": ordered_tools and sequence == expected
            and all(r.get("trigger") == "auto" for r in records if r.get("event") in {"PreCompact", "PostCompact"})
            and (not repaired or any(r.get("event") == "SessionStart" and r.get("source") == "compact"
                                     and r.get("additional_context") is True for r in records)),
        "product_hook_decision": bool(decision) and bool(records)
            and all(r.get("returncode") == 0 for r in records),
        "no_unexpected_tools": not forbidden,
        "terminal_state": (events.get("event_types", {}).get("turn.completed") == 1
                           and not events.get("event_types", {}).get("turn.failed")) if repaired
                           else not events.get("event_types", {}).get("turn.completed"),
    }
