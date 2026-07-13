from __future__ import annotations

import json
import sys

from plan_anvil_checkpoint import validate_checkpoint_for_run
from plan_anvil_hooklib import active_run_for_event, read_event


def _stop(reason: str) -> None:
    json.dump(
        {
            "continue": False,
            "stopReason": reason,
        },
        sys.stdout,
    )
    sys.stdout.write("\n")


def main() -> int:
    event = read_event()
    active = active_run_for_event(event)
    if active is None:
        return 0
    state = active.state
    if not isinstance(state.get("revision"), int) or not isinstance(state.get("next_action"), dict):
        _stop("PlanAnvil canonical state is invalid. Repair and persist state before compaction.")
        return 0

    validation = validate_checkpoint_for_run(active)
    if not validation.ok:
        details = "; ".join(validation.reasons)
        _stop(
            "Create or repair a durable, schema-valid PlanAnvil checkpoint before compaction. "
            f"Checkpoint validation failed: {details}."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
