# C16 — Capability evidence

- Expected behavior: The Git probe reports refs, branches, worktrees, index, commits and cleanup accurately.
- Source: `CONTRACT_DEFINED`
- Release-gating: `yes`
- Current result: `BLOCKED`
- Qualification attempt: `2026-08-28`
- Deterministic support: reversible probe, source preservation, cleanup and hook-failure classification tests passed in run #24.
- Live blocker: no authenticated Codex runtime is available to execute the required matrix under supported Codex permission modes.

Do not change the result to `REPRODUCED` until the complete sanitized live package exists.
