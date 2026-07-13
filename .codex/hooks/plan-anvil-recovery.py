from __future__ import annotations

from plan_anvil_checkpoint import validate_checkpoint_for_run
from plan_anvil_hooklib import active_run_for_event, context, read_event


def main() -> int:
    event = read_event()
    active = active_run_for_event(event)
    if active is None:
        return 0
    state = active.state
    next_action = state.get("next_action") if isinstance(state.get("next_action"), dict) else {}
    checkpoint = validate_checkpoint_for_run(active)
    checkpoint_text = (
        f"Validated checkpoint: {checkpoint.path}."
        if checkpoint.ok
        else "Checkpoint is not valid; do not continue until repaired: " + "; ".join(checkpoint.reasons) + "."
    )
    message = (
        f"Recover PlanAnvil from files: read {active.run_root / 'manifest.json'}, "
        f"{active.run_root / 'state.json'}, ignored local-state.json, profiles, and the latest valid checkpoint; "
        f"then reconcile Git before continuing. Current state is {state.get('status')}; "
        f"next action is {next_action.get('type')} targeting {next_action.get('target')}. "
        f"{checkpoint_text}"
    )
    context(str(event.get("hook_event_name") or "SessionStart"), message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
