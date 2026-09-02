# C13 — Capability evidence

- Expected behavior: `SubagentStart` can add context but `continue: false` does not stop subagent startup.
- Source: `DOCUMENTED`
- Release-gating: `yes`
- Current result: `BLOCKED`
- Qualification attempt: `2026-09-02`
- Documentation check: `PASS` against current Codex hooks documentation.
- Baseline: `2.3`.
- Qualification transport: ephemeral-first; only the recognized parent-thread registration failure permits a controlled non-ephemeral retry with a synthetic home-scoped `fixture_agent` in a disposable `CODEX_HOME`, while the real `SubagentStart` hook remains project-scoped.
- Latest diagnostic: run #8 confirmed the ephemeral parent-thread blocker and separately showed that a project-scoped synthetic agent can fail before `SubagentStart`; neither observation counts as semantic reproduction.
- Live blocker: a new full baseline-2.3 run must reach the real `SubagentStart` boundary and verify `additionalContext`, `continue=false`, child context echo, repository immutability, session cleanup, and auth-metadata invariants.

Do not change the result to `REPRODUCED` until the complete sanitized live package exists.
