from __future__ import annotations
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
