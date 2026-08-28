# C11 — Capability evidence

- Expected behavior: Project instructions follow documented directory scope and precedence.
- Source: `DOCUMENTED`
- Release-gating: `yes`
- Current result: `BLOCKED`
- Qualification attempt: `2026-08-28`
- Documentation check: `PASS`; current docs define root-to-CWD discovery, `AGENTS.override.md` precedence, fallbacks and nearest-guidance override behavior.
- Deterministic support: instruction-map and conflict tests passed in run #24.
- Live blocker: no authenticated Codex runtime is available to record actual instruction sources.

Do not change the result to `REPRODUCED` until the complete sanitized live package exists.
