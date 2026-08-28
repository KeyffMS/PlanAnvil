# C03 — Capability evidence

- Expected behavior: Generated execution contracts require an explicit flat direct-child topology without relying on a Codex nesting-depth setting.
- Source: `CONTRACT_DEFINED`
- Release-gating: `yes`
- Current result: `BLOCKED`
- Qualification attempt: `2026-08-28`
- Baseline correction: current Codex documentation does not document `agents.max_depth`; PlanAnvil now enforces flat topology in deterministic contract validation.
- Deterministic support: execution-contract topology tests passed in run #24; qualification adds a regression rejecting legacy-depth-only wording.
- Live blocker: no authenticated Codex runtime is available to capture the required subagent event tree.

Do not change the result to `REPRODUCED` until the complete sanitized live package exists.
