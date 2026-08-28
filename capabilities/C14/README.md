# C14 — Capability evidence

- Expected behavior: Planning isolation preserves the source branch, SHA, index and files.
- Source: `CONTRACT_DEFINED`
- Release-gating: `yes`
- Current result: `BLOCKED`
- Qualification attempt: `2026-08-28`
- Deterministic support: planning-worktree isolation, source-preservation and destination-safety tests passed in run #24.
- Live blocker: the repository policy requires a complete committed capability package tied to an actual Codex run.

Do not change the result to `REPRODUCED` until the complete sanitized live package exists.
