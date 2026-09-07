from __future__ import annotations
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
