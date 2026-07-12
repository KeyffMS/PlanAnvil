from __future__ import annotations

from plan_anvil_hooklib import active_run_for_event, context, read_event


def main() -> int:
    event = read_event()
    agent = str(event.get("agent_type") or "")
    active = active_run_for_event(event)
    pointer = ""
    if active is not None:
        pointer = f" Canonical run state is {active.run_root / 'state.json'}; verify it before work and do not treat conversation context as state."
    if agent == "plan_anvil_profiler":
        context(
            "SubagentStart",
            "Remain read-only. Read assigned instruction files completely, verify hashes, gather repository evidence, and return facts with repository-relative paths. Do not author or execute implementation." + pointer,
        )
    elif agent == "plan_anvil_reviewer":
        context(
            "SubagentStart",
            "Perform one fresh blind review from the supplied bundle only. Do not request planner reasoning, edit files, or execute implementation. Return a PASS/FAIL conclusion and concrete findings." + pointer,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
