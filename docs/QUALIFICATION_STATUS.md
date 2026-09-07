# Qualification status

## Recorded live result

Full run #25 (`34060321283`) passed baseline 2.3 C01-C16 on product source
`d0384f76bc4150d33bb8f51ef5981f3243b3cfb3`, Codex CLI 0.153.4,
`gpt-5.6-sol`, Debian 13. C04 is informational. The immutable original archive,
summary, checksums and caveats are in `qualifications/34060321283/`.

## Implemented closure

PR #34 merged the finite C08 repair and the reviewed evidence into main at
`ba3f56a644a385c8aa2e8e5c9c934999184cc282`. PR CI #118 and post-merge CI #119
passed all eight jobs, including actual Codex CLI loopback conformance. These
are implementation/integration checks, not a new live-model result.

The historical positive C08 trial timed out after meeting its narrow unblock
assertion. It remains unchanged in the archive. The finite replacement requires
the same canonical run to stop at PreCompact without a checkpoint, then, after
outer checkpoint repair, complete pressure -> compact recovery -> finish with
exit zero. Timeout or incomplete telemetry cannot pass.

C13 passed in the explicitly allowed project-scoped non-ephemeral fallback.
Ephemeral spawning is not claimed as working. The product .agents/.codex payload
and the C09/C10/C13 runtime paths are unchanged by this closure.

## Required operator action

The automated full launch #26 (`34109662176`) used the repaired main commit,
but the self-hosted runner's job-start policy rejected its initiating actor:

```text
PlanAnvil runner policy denied this job: initiating actor is not allowed
```

The hook exited 77 before runner preflight, fixture preparation or any Codex
trial. This run has no new capability evidence and is not a C08 test failure.
Do not change the runner allowlist, spoof the actor or relax the trusted-workflow
policy to make an automated launch pass.

An operator whose account is allowed by the runner policy must start a NEW run:

**Actions -> PlanAnvil Codex qualification -> Run workflow -> main -> full**.

Use Run workflow, not Re-run of the denied automated run. GitHub Actions
orchestrates the job; all model-backed trials run on the existing authenticated
self-hosted runner, not on a GitHub-hosted machine.

## Evidence required for publication

The current production validator requires ONE complete, source-bound full-run
archive, exact matching current capability packages, unchanged qualified product
bytes, and finite C08 stop/repair proof in that same archive. Therefore the next
publication proof must be a successful new `full` run. The `c08` mode remains a
useful targeted diagnostic, but its partial archive alone cannot close the
production gate. Do not splice it into or relabel the immutable #25 archive.

After success, review and verify the new sanitized archive, preserve it under
`qualifications/<run-id>/`, import its exact C01-C16 packages, and update
`qualifications/index.json` through a protected PR. Keep #25 unchanged as history.
Record the actually executed source SHA, not the later import commit. Run the
strict release check on a clean tree after import. No production tag or release
has been created by these preparation steps.

## Verification layers

Unit/process tests and pinned real-CLI loopback tests check implementation and
protocol behavior. Only the authenticated self-hosted qualification workflow
provides live-model evidence. Newly materialized templates always start BLOCKED;
archived evidence cannot silently qualify a fresh fixture or changed product.

## Audit index

- `CODEX_CAPABILITY_QUALIFICATION_2026-08-28.md`: historical prerequisite-limited attempt.
- `CODEX_QUALIFICATION_EXECUTION_AUDIT_2026-09-05.md`: C13 argv and C10 worktree discovery.
- `CODEX_RECOVERY_DELIVERY_AUDIT_2026-09-05.md`: supported context delivery and diagnostics.
- `CODEX_C09_FINITE_RECOVERY_AUDIT_2026-09-06.md`: completed finite C09 repair.
- `CODEX_C08_CLOSURE_AUDIT_2026-09-07.md`: finite C08 and evidence closure.

Older harness modules are retained because v7 still imports them. They are not
independent supported entry points. Do not delete imported layers as cosmetic cleanup.
