# C04 — Capability evidence

- Expected behavior: Codex subagent workflows use current agent enablement/concurrency settings; PlanAnvil does not require nested descendants.
- Source: `DOCUMENTED`
- Release-gating: `no` for baseline 2.2
- Current result: `BLOCKED`
- Qualification attempt: `2026-08-28`
- Documentation check: `PASS`; current docs expose `agents.enabled` and `agents.max_concurrent_threads_per_session`, not a nesting-depth knob.
- Live blocker: no authenticated Codex runtime is available for subagent spawning evidence.

This capability is informational for PlanAnvil 2.2 because generated execution deliberately requires a flat direct-child topology.
