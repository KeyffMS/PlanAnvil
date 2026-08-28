# C12 — Capability evidence

- Expected behavior: `project_doc_max_bytes` can truncate automatic instruction loading.
- Source: `DOCUMENTED`
- Release-gating: `yes`
- Current result: `BLOCKED`
- Qualification attempt: `2026-08-28`
- Documentation check: `PASS`; current configuration/AGENTS documentation defines the combined instruction byte limit.
- Deterministic support: explicit read/hash freshness tests passed in run #24.
- Live blocker: no authenticated Codex runtime is available for a truncation fixture.

Do not change the result to `REPRODUCED` until the complete sanitized live package exists.
