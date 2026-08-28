# C09 — Capability evidence

- Expected behavior: Compaction is allowed after checkpoint creation without a permanent stop loop.
- Source: `CONTRACT_DEFINED`
- Release-gating: `yes`
- Current result: `BLOCKED`
- Qualification attempt: `2026-08-28`
- Deterministic support: valid checkpoint acceptance and recovery tests passed in run #24.
- Live blocker: no authenticated Codex runtime is available to demonstrate stop → checkpoint → compact → recover without a loop.

Do not change the result to `REPRODUCED` until the complete sanitized live package exists.
