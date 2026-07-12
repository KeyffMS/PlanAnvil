from __future__ import annotations

import json
import sys

from plan_anvil_hooklib import active_run_for_event, read_event


def main() -> int:
    event = read_event()
    active = active_run_for_event(event)
    if active is None:
        return 0
    state = active.state
    if not isinstance(state.get("revision"), int) or not isinstance(state.get("next_action"), dict):
        json.dump(
            {
                "continue": False,
                "stopReason": "PlanAnvil canonical state is invalid. Repair and persist state before compaction.",
            },
            sys.stdout,
        )
        sys.stdout.write("\n")
        return 0
    if state.get("mode") == "PLAN_EXECUTION" and not state.get("last_checkpoint"):
        json.dump(
            {
                "continue": False,
                "stopReason": "Create and validate a durable PlanAnvil execution checkpoint before compaction.",
            },
            sys.stdout,
        )
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
