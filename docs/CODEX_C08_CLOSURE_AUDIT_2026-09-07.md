# C08 and evidence closure — 2026-09-07

## Proven baseline and remaining defect

Full live run 34060321283 on d0384f76bc4150d33bb8f51ef5981f3243b3cfb3
reproduced C01-C16 under baseline 2.3. Its positive C08 probe reported 21
PreCompact and 20 PostCompact events before timeout. The original assertions
only required a temporary stop and subsequent unblock; the old evaluator ignored
invocation errors after seeing a successful PostCompact. The archive is preserved
unchanged, including that limitation and the permitted C13 fallback.

The active C08 adapter forced a 40-token threshold and repeated large reads.
Canonical next_action still described MAP_INSTRUCTIONS. These inspectable setup
conflicts are repaired. They do not establish all commands in the historical
trace or prove an upstream Codex deadlock.

## Source and contract review

Pinned openai/codex rust-v0.153.4: core/src/session/turn.rs and
session/context_window.rs retain follow-up-dependent automatic compaction;
core/src/compact.rs surrounds successful compaction with real PreCompact and
PostCompact. PreCompact stop aborts the turn. hook_runtime.rs supplies recovery
through SessionStart(source=compact), not PostCompact additionalContext.
config loader redirects linked-worktree hook declarations to the root checkout.
The official hook/config references were checked on 2026-09-07. Neither contract
promises that a repeated, conflicting fixture workload will terminate.

## Repair and acceptance

One real canonical run, two independent CLI invocations: missing-checkpoint
pressure must stop at PreCompact; then the outer harness creates the real
checkpoint and the repaired invocation runs pressure -> one automatic compaction
-> real SessionStart(compact) recovery -> finish -> completed positive response.
The fixed source hook configuration excludes startup context before bootstrap,
so the deliberate negative trial is not instructed to repair its checkpoint.
The compact recovery handler and all product decisions remain unchanged.

The finite pressure output and 8192 body-after-prefix threshold apply only to
C08's disposable fixture; 600-second deadlines remain unchanged. All three real
commands (one negative, two positive), command receipts, ordered automatic
lifecycle, checkpoint validity, hook exit status, process termination/cleanup and
source/planning Git plus file bytes are verified. Partial traces, timeouts,
extra/repeated tools, wrong lifecycle, invalid receipts or incomplete diagnostics
cannot pass. A negative Codex exit 1 is accepted only with the proven real
checkpoint stop, no PostCompact and complete process cleanup.

C09/C10/C13 runtimes, product .agents/.codex content, signing, sandbox, approvals,
auth ownership, runner trust policy, and the evidence packer are unchanged.

## Evidence separation and release guard

The original #25 packages are committed with immutable archive/provenance.
Fresh materialization resets its index to BLOCKED/NOT_RUN instead of inheriting
historical success. Production checks additionally require finite C08 evidence,
exact archived package bytes, complete full-run provenance and the unchanged
qualified product-file inventory. Offline/simulated passes cannot promote live
capabilities. The qualified source SHA stays the executed SHA, not the later
metadata/import commit.

## Test boundary

Executed process tests use real install/start/Git/checkpoint/hook scripts; the
model process alone is replaced. The separate pinned real-CLI test uses a loopback
Responses peer and is not live-model qualification. Final confirmation is the
existing workflow on the authenticated self-hosted runner. All prior required CI
jobs remain required; the protected distribution check depends on the real-CLI
conformance result, rather than relying on an optional new check.

Historical controllers and audits remain because active v7 imports the layers.
No signed production tag or public release is created by this preparation.
