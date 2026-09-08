# Qualification status

## Current reviewed full result

**Live qualification is complete for the tested configuration.** Owner-initiated
full run #27 (`34140846679`) passed baseline 2.3 C01-C16 on executed source
`a9cdcdc1e0cad70e88b60869e75e4166046dd306`, Codex CLI 0.153.4,
model `gpt-5.6-sol`, Debian GNU/Linux 13. C04 is informational; fifteen
capabilities are required. The full run reports `release_gate_passed=true`.
All model-backed trials ran on the authenticated self-hosted runner.

The original archive, exact summary and verified provenance are preserved in
`qualifications/34140846679/`. `qualifications/index.json.current_run` points to
that run. Current `capabilities/C01` through `C16` are exact archive copies,
not rewritten observations or a combination of partial runs. The executed source
SHA remains the original SHA, never the later evidence-import commit.

## C08 closure and recovery regressions

C08 completed its finite stop/repair protocol in the same canonical run:

- Without a checkpoint: one completed pressure command, an actual automatic
  PreCompact `continue=false`, expected process exit 1 after 10.643 seconds,
  no PostCompact and no timeout.
- After the outer harness created a real valid checkpoint: pressure, one
  automatic PreCompact/PostCompact cycle, SessionStart(source=compact), finish
  reconciliation and positive structured completion; exit 0 after 36.265 seconds,
  no timeout. All nine positive protocol checks passed.

C09 completed all three reconciliations and two ordered automatic recovery
cycles with exit 0 in 60.679 seconds. Both independent C10 context-delivery
probes completed with exact recovery values and exit 0. Process cleanup and
checkpoint/source immutability checks passed for the recovery probes.

There are no recorded `timeout=true` values in the current actual evidence.
This is not a guarantee of future model behavior or support for untested
Codex/model/operating-system combinations.

## Retained compatibility limitation

C13 passed using the explicitly allowed project-scoped non-ephemeral fallback
after the recognized ephemeral parent-thread failure. Agent and SubagentStart
hook remained project-scoped; child context, cleanup and authentication
invariants passed. Ephemeral spawning is not claimed as working.

## Integrity and publication boundary

The archive contains 166 manifest-listed files plus the manifest, including
three hidden fixture files. All SHA-256 checks, per-capability package validation
and source identities were verified before import. The qualified .agents/.codex
product bytes, runtime implementations, permission policy and release guards
are unchanged by this evidence/documentation update.

On a clean checkout, run `python tools/validate_capabilities.py` and
`python tools/release_check.py` without `--candidate`. The latter requires the
complete full-run archive, exact packages, unchanged qualified product bytes
and finite C08 completion. Freshly materialized unexecuted templates still start
BLOCKED and cannot inherit the archived success.

No additional live run is required merely to record these same results or
update documentation. Requalify when relevant product/runtime inputs change.
Production publication remains a separate owner-authorized verified signed
annotated tag and release workflow, as described in `RELEASE.md`. No production
tag or release is created by the evidence import.

## Preserved history

Run #25 (`34060321283`, source `d0384f76bc4150d33bb8f51ef5981f3243b3cfb3`)
passed the older narrow assertions but its positive C08 trial later timed out.
Its original archive, summary, provenance and caveat remain unchanged under
`qualifications/34060321283/`; it is not the current publication evidence.

PR #34 merged the finite C08 repair. Automated run #26 (`34109662176`) was
rejected by the local initiating-actor policy before Codex. It provides no live
result. The owner-initiated #27 completed without changing or bypassing that
policy. PR #35 clarified the requirement for one complete full archive.

## Verification layers and audit index

Unit/process tests and real-CLI loopback conformance check implementation and
protocol behavior. Only the authenticated self-hosted run supplies live-model
evidence. The archived full result does not imply execution of every possible
application plan; PlanAnvil generates and validates plans, never implements them.

- `CODEX_CAPABILITY_QUALIFICATION_2026-08-28.md`: historical prerequisite-limited attempt.
- `CODEX_QUALIFICATION_EXECUTION_AUDIT_2026-09-05.md`: C13 argv and C10 worktree discovery.
- `CODEX_RECOVERY_DELIVERY_AUDIT_2026-09-05.md`: context delivery and diagnostics.
- `CODEX_C09_FINITE_RECOVERY_AUDIT_2026-09-06.md`: finite C09 repair.
- `CODEX_C08_CLOSURE_AUDIT_2026-09-07.md`: finite C08 implementation.

Older harness modules remain active v7 dependencies, not separate supported
entry points. They must not be removed as cosmetic cleanup.
