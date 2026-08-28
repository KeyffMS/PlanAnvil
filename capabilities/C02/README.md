# C02 — Capability evidence

- Expected behavior: `allow_implicit_invocation: false` disables implicit invocation while explicit `$skill` invocation remains available.
- Source: `DOCUMENTED`
- Release-gating: `yes`
- Current result: `BLOCKED`
- Qualification attempt: `2026-08-28`
- Documentation check: `PASS`; repository metadata is configured for explicit-only activation.
- Deterministic support: `test_skill_metadata_requires_explicit_activation` passed in GitHub Actions run #24.
- Live blocker: no authenticated Codex runtime is available for implicit-vs-explicit prompt trials.

Do not change the result to `REPRODUCED` until the complete sanitized live package exists.
