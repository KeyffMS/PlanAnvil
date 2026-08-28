# C06 — Capability evidence

- Expected behavior: `PreToolUse` covers supported local function-tool paths but not every equivalent path.
- Source: `DOCUMENTED`
- Release-gating: `yes`
- Current result: `BLOCKED`
- Qualification attempt: `2026-08-28`
- Documentation check: `PASS`; current hooks documentation lists supported shell, patch, MCP and local-function paths plus hosted/specialized exceptions.
- Deterministic support: hook guard tests passed in run #24.
- Live blocker: no authenticated Codex runtime is available to capture supported and bypass-path hook events.

Do not change the result to `REPRODUCED` until the complete sanitized live package exists.
