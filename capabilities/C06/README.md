# C06 — Capability evidence

- Expected behavior: `PreToolUse` covers Codex-supported local hook adapters, while deterministic postconditions cover file-change transports that are not guaranteed to produce a project `PreToolUse` event.
- Source: `DOCUMENTED_AND_SOURCE_VERIFIED`
- Release-gating: `yes`
- Current result: `BLOCKED`
- Qualification target: Codex CLI `0.152.x`

## Codex 0.152 contract

Codex 0.152 maps function-call `exec_command` into the canonical `Bash` `PreToolUse` payload. Its native `apply_patch` hook adapter is attached to the freeform/custom apply-patch handler. PlanAnvil therefore treats a hook as an early guard, not a complete mutation ledger.

A release-gating live qualification must establish both boundaries:

1. a real supported `exec_command` call produces a project `PreToolUse` observation with canonical tool name `Bash`;
2. a real direct file-change attempt is either blocked by the hook boundary or is detected immediately by the deterministic Git/filesystem postcondition before another modifying action.

The second assertion is a product safety requirement. Missing `PreToolUse` telemetry never makes a completed mutation implicitly safe.

Do not change the result to `REPRODUCED` until the complete sanitized live package establishes the hook-plus-postcondition boundary on the target Codex runtime.
