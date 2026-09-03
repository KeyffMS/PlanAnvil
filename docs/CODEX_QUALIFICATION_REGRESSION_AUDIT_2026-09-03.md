# Codex qualification regression audit — 2026-09-03

## Scope

This audit was performed after full live qualification run #9 on `main` (`7bf68e3fa8d6caff8ed8af1bf98f6be30d4670cd`). It covers the active live qualification controller, harness versions v1-v6, workflow transport, capability evidence materialization, and the remaining C03/C06/C08/C09/C13/C16 failures.

The goal is to remove systemic harness regressions before another self-hosted full qualification run. No result from run #9 is reclassified merely to make the release gate pass.

## Systemic findings

### A1 — chained runtime dispatch is unsafe

The active path is a chain of `live_codex_qualification.py` plus six wrapper modules. Several wrappers own the same capabilities, snapshot previous dispatch functions, and mutate `base.capability_runtime` globally. This makes effective capability ownership implicit and allows later fixes to regress earlier behavior without a single authoritative dispatch table.

**Decision:** the active workflow must move to one current suite with an explicit, unique C01-C16 runtime map. Historical wrappers may remain for provenance but must not participate in the current workflow path.

### A2 — model planning/evaluation is used for deterministic assertions

The generic controller asks a planner model to build fixtures and an evaluator model to classify evidence. That is useful only where the capability genuinely requires model behavior. It is harmful for deterministic assertions because evidence can be complete while the evaluator still marks it incomplete. C16 run #9 is the concrete regression: all three Git trials matched their expected classifications and cleanup invariants, but the evaluator blocked on missing sanitized diagnostic basis.

**Decision:** C03, C06, C08, C09, C13, and C16 use outer deterministic classification in the current suite. Model output may be evidence of runtime behavior, never the authority for a deterministic final decision.

### A3 — existing regression tests overfit source text

Tests for v4-v6 mostly assert that source strings exist. They do not prove effective capability ownership, subprocess transport construction, exact session resume behavior, or classification logic.

**Decision:** add behavioral tests for the current dispatch table, stateful session command construction, exact thread-id handling, C03 contract validation, C06 layered classification, C16 diagnostic classification, and prohibited security flags.

## Capability findings

### C03 — excessive lifecycle coupling

C03 is `CONTRACT_DEFINED`: the generated execution contract must require a flat direct-child topology and must not rely on a Codex nesting-depth setting. The current generic trial unnecessarily enters the full PlanAnvil lifecycle and therefore depends on the mandatory Git capability probe. Run #9 stopped before contract generation because Git metadata was read-only.

PlanAnvil already has deterministic `execution_contract_findings()` validation for flat direct-child topology, required roles, single-modifier behavior, retry structure, evidence cycle and approval boundaries.

**Decision:** C03 becomes a deterministic contract probe. It validates one known-good execution-contract fixture and one deliberately broken nested/depth-dependent fixture. It does not run the unrelated Git bootstrap.

### C06 — must distinguish Codex hook runtime from PlanAnvil guard

Run #9 completed a real direct `apply_patch` file change but recorded zero `PreToolUse` events. Codex 0.152.0 source exposes a `PreToolUsePayload` for `apply_patch`, and the registry invokes `run_pre_tool_use_hooks` for such payloads. PlanAnvil's matcher also includes `apply_patch`.

**Decision:** C06 is split into two ordered layers:

1. a minimal neutral project-scoped `PreToolUse` hook with matcher `^apply_patch$`, no PlanAnvil guard logic;
2. the actual PlanAnvil guard path plus mandatory outer Git postcondition detection.

If layer 1 fails after the direct patch executes, C06 remains a runtime `FAILED` and the PlanAnvil layer cannot hide it. If layer 1 passes but the PlanAnvil layer fails, the result is a PlanAnvil/harness defect.

### C08/C09 — one-turn ephemeral trigger was invalid

The v4 harness attempted to force automatic compaction inside a single `codex exec --ephemeral` invocation. Codex 0.152.0's own tests state that a single over-limit completion may wait until the next user message before auto-compaction. The CLI exposes `codex exec resume <SESSION_ID>` for continuing a persisted non-interactive session.

**Decision:** C08/C09 use controlled, disposable multi-turn sessions. The current suite:

- creates a private disposable `CODEX_HOME`;
- bridges file-backed auth only by symlink, without reading/copying auth content;
- starts a non-ephemeral session and parses the exact `thread.started` id from JSONL;
- resumes only that exact id, never `--last`;
- keeps approval `never`, the required sandbox, and model-tool network disabled;
- removes the entire disposable home and verifies auth metadata is unchanged.

C08 proves invalid recovery state stops/delays `PreCompact`, then repairs the checkpoint and proves compaction can proceed. C09 proves at least two real compaction cycles and a normal tool action after the second cycle.

Because persistence is required to reach the documented lifecycle boundary, this is qualification transport, not a relaxation of the security boundary.

### C13 — transport/discovery is now separated from hook semantics

Run #9 proved that the baseline-2.3 fallback can discover and start the home-scoped `fixture_agent`: the child returned `C13_CONTEXT_MISSING`. Thus parent-thread persistence and home-scoped role discovery are no longer the remaining blockers.

Codex 0.152.0 applies role overrides to an existing parent-derived config layer stack; project layers are preserved. `SubagentStart` matches on `agent_type`, can add context, and ignores `continue:false` as a startup blocker.

**Decision:** keep the ephemeral-first / recognized-parent-thread-error fallback. The fallback continues to use a disposable home-scoped role but the project-scoped hook remains the semantic assertion. Classification is outer-deterministic: child echo with the opaque injected proof is `REPRODUCED`; child starts without that context after a verified matching hook configuration is a real semantic `FAILED`; transport/preflight failure before that boundary is `BLOCKED`.

### C16 — evidence loss, not product failure

Run #9 produced the expected `GIT_READY`, `GIT_SIGNING_BLOCKED`, and `GIT_HOOK_BLOCKED` outcomes with clean cleanup and unchanged source snapshots. The evaluator blocked because sanitized evidence omitted the diagnostic basis.

**Decision:** preserve only privacy-safe diagnostic booleans/classes (`git_exit_nonzero`, expected fixture marker observed, diagnostic class) and classify deterministically without an evaluator model.

## Transport contract change

Baseline 2.3 allowed a narrowly controlled non-ephemeral fallback for C13. The audit shows C08 and C09 also require controlled persistence to reach the tested multi-turn compaction lifecycle. The current qualification contract therefore becomes baseline 2.4:

- ephemeral remains the default for independent capabilities;
- C08/C09 may use isolated persisted sessions because persistence is required to reproduce the lifecycle under test;
- C13 retains ephemeral-first behavior and uses isolated persistence only after the recognized parent-thread registration failure;
- exact thread ids are used; `--last` is forbidden;
- disposable session state is mandatory and cleanup/auth metadata verification is fail-closed.

## Security invariants

The regression repair must not introduce:

- `--dangerously-bypass-approvals-and-sandbox`;
- `danger-full-access`;
- privileged containers or `SYS_ADMIN`;
- model-tool network access;
- automatic pushes from the self-hosted runner;
- live qualification on PR or untrusted code.

Approval remains `never`; sandbox mode remains capability-specific least privilege; project hook trust bypass remains limited to vetted disposable qualification fixtures.

## Exit criteria before another full live run

A new full self-hosted run is allowed only after all of the following pass on hosted CI:

1. one explicit current C01-C16 dispatch table with unique ownership;
2. no active workflow dependency on the v1-v6 wrapper chain;
3. deterministic C03/C16 classification tests;
4. C06 minimal-hook versus PlanAnvil-guard layered classification tests;
5. C08/C09 exact-thread-id multi-turn command/state-machine tests and cleanup tests;
6. C13 fallback and semantic-boundary classification tests;
7. full capability materialization/validation and release-candidate checks;
8. all existing Ubuntu/macOS/Windows core checks.
