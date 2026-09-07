# Qualification status

## Recorded result

Full run #25 (`34060321283`) passed baseline 2.3 C01-C16 on product source
`d0384f76bc4150d33bb8f51ef5981f3243b3cfb3`, Codex CLI 0.153.4,
`gpt-5.6-sol`, Debian 13. C04 is informational. The immutable original archive,
summary, checksums and caveats are in `qualifications/34060321283/`.

## Closure in progress

The historical positive C08 trial timed out after meeting its narrow unblock
assertion. It remains unchanged in the archive. The current finite replacement
requires the same canonical run to stop at PreCompact without a checkpoint,
then, after outer checkpoint repair, complete pressure -> compact recovery ->
finish with exit zero. Timeout or incomplete telemetry cannot pass.
The replacement is not yet claimed as live evidence. Production release checks
require its actual committed finite evidence and qualified product identity.

C13 passed in the explicitly allowed project-scoped non-ephemeral fallback.
Ephemeral spawning is not claimed as working. The current product .agents/.codex
payload and the C09/C10/C13 runtime paths are unchanged by this closure.

## Verification layers

Unit/process tests and the pinned real-CLI loopback tests check implementation
and protocol behavior. Only the authenticated self-hosted qualification workflow
provides live-model evidence. Newly materialized templates always start BLOCKED;
archived evidence cannot silently qualify a fresh fixture or changed product.

## Audit index

- `CODEX_CAPABILITY_QUALIFICATION_2026-08-28.md`: historical prerequisite-limited attempt.
- `CODEX_QUALIFICATION_EXECUTION_AUDIT_2026-09-05.md`: C13 argv and C10 worktree discovery.
- `CODEX_RECOVERY_DELIVERY_AUDIT_2026-09-05.md`: supported context delivery and diagnostics.
- `CODEX_C09_FINITE_RECOVERY_AUDIT_2026-09-06.md`: completed finite C09 repair.
- `CODEX_C08_CLOSURE_AUDIT_2026-09-07.md`: remaining C08 and evidence closure.

Older harness modules are retained because v7 still imports them. They are not
independent supported entry points. Do not delete imported layers as cosmetic cleanup.
