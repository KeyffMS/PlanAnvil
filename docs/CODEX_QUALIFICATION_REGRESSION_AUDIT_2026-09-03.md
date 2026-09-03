# Codex qualification regression audit — 2026-09-03

## Scope

This audit was completed before another qualification or CI run. It reviews the live-qualification controller chain, the full sanitized evidence from qualification run #9 (`33732852918`, source commit `7bf68e3fa8d6caff8ed8af1bf98f6be30d4670cd`), and the Codex 0.152.0 runtime contracts relevant to C03, C06, C08, C09, C13, and C16.

The purpose is to remove harness-induced failure modes before spending another self-hosted Codex run.

## Run #9 control result

Run #9 completed the controller and uploaded a valid evidence artifact. It produced 10/16 `REPRODUCED` results. The six non-reproduced capabilities were C03, C06, C08, C09, C13, and C16.

A capability is treated as a harness defect only when the evidence and controller establish that the test itself prevented or obscured the behavior being measured. Contradictory runtime behavior is not relabeled as a harness defect.

## Findings

### R1 — read-only hook telemetry can break the hook under test (C08, C09, C13)

Severity: critical.

The v4/v5 proxies execute the real hook, then write recorder JSONL under `.pursue/` inside the fixture repository, and only after that write forward the real hook stdout/stderr and return code to Codex. C08, C09, and C13 execute these paths with `sandbox=read-only`. A failed recorder write can therefore terminate the proxy before the real hook result reaches Codex.

Repair: telemetry moves to a disposable external sidecar, recorder I/O is fail-open, and the real hook stdout/stderr/return code is always forwarded. Missing telemetry may block qualification but may never change hook semantics.

### R2 — C08/C09 auto-compaction must be independent of recorder success

Severity: high.

Run #9 showed zero PreCompact/PostCompact records. Because R1 can suppress the real hook response, that absence does not distinguish “no compaction” from “compaction attempted but proxy failed”.

Repair: fix R1 first, retain redundant project + CLI auto-compaction configuration, use deterministic low `body_after_prefix` thresholds, and require real sidecar PreCompact/PostCompact records. C09 still requires two complete compaction cycles and a real tool call after the second PostCompact.

### R3 — C13 transport/discovery fallback works; remaining result is contaminated by R1

Severity: high.

Run #9 established that the baseline-2.3 non-ephemeral fallback creates a session and starts the home-scoped `fixture_agent`: the child returned `C13_CONTEXT_MISSING`. Parent-thread persistence and home-scoped agent discovery are therefore no longer the immediate blocker. The same trial recorded zero SubagentStart proxy events, but that proxy uses the R1 recorder pattern.

Repair: retain ephemeral-first, the known-error-only fallback, the home-scoped fallback agent, and the project-scoped hook; move telemetry to the external fail-open sidecar; require exactly one real SubagentStart record, `continue=false`, `additionalContext`, child echo of the opaque outer proof, repository immutability, cleanup and auth-metadata invariants.

If the repaired probe still starts the child without a SubagentStart record/context proof, that becomes runtime evidence rather than a recorder artifact.

### R4 — C03 uses an implicit workspace Git repository whose `.git` remains protected

Severity: high.

C03 reached the real PlanAnvil bootstrap, but the mandatory reversible Git probe could not create a temporary ref. `workspace-write` does not make the implicit workspace `.git` metadata writable.

Repair: use a command-driver repository and place the synthetic PlanAnvil source repository in an explicit auxiliary writable root. Run the real outer `plan_anvil.py start`, assert source branch/head/index/file preservation and cleanup, verify current agents configuration and flat direct-child execution contract, and calculate C03 deterministically in the outer harness rather than with a model evaluator.

### R5 — C16 has successful real trials but the model evaluator discards diagnostic basis

Severity: critical false-blocker.

Run #9 produced PASS for `GIT_READY`, `GIT_SIGNING_BLOCKED`, and `GIT_HOOK_BLOCKED`, with empty snapshot changes and cleanup errors. The capability was nevertheless marked `BLOCKED` because the evaluator requested diagnostic basis that the sanitized trial payload omitted.

The product probe already returns bounded per-step diagnostics in `steps[].detail` and the fixtures use deterministic markers.

Repair: execute/parse the real probe in the outer harness, reduce controlled diagnostics to booleans such as `signing_diagnostic_observed` and `hook_diagnostic_observed` before sanitization, and calculate C16 deterministically. Raw stderr, private paths and session data are not retained.

### R6 — C06 must not be converted to green without an isolated runtime repro

Severity: high.

Run #9 completed a real direct `apply_patch` file change while the PlanAnvil PreToolUse recorder observed zero `apply_patch` events. This trial used `workspace-write`, so R1 does not explain the result. Codex 0.152.0 defines a PreToolUse payload for direct `apply_patch`, and PlanAnvil's matcher includes `apply_patch`.

Repair: retain the integrated PlanAnvil trial and add a second minimal repository containing only one project-scoped `PreToolUse` hook matching `^apply_patch$`. If the minimal hook fires but PlanAnvil does not, C06 remains `BLOCKED` as an integration defect. If even the minimal current-runtime hook does not fire after a successful direct patch, C06 is `FAILED`. Only both hook observations plus mandatory postcondition detection may produce `REPRODUCED`.

### R7 — model planner/evaluator dependence remains in release-gating paths

Severity: high.

C03 still used the generic model-driven fixture planner/evaluator and C16 delegated its final decision to the evaluator. This creates avoidable non-determinism.

Repair: C03 and C16 join C06/C08/C09/C13 as outer-deterministic release-gate decisions. Model output may supply live runtime observations but is not the sole arbiter when the outer harness can directly verify the assertion.

### R8 — wrapper-chain growth increases regression risk

Severity: medium.

The controller already chains historical overrides through v1-v6. Adding v7 would make ownership harder to audit.

Repair: keep `live_codex_qualification_harness_v6.py` as the workflow entrypoint. It explicitly owns C03, C06, C08, C09, C13, and C16 through one regression helper and delegates all other capabilities to the already-proven chain.

### R9 — previously reproduced capabilities

Run #9 evidence for C01, C02, C04, C05, C07, C10, C11, C12, C14, and C15 was reviewed for the same controller-induced false-green patterns. No release-gate assertion was found to depend on the failing recorder pattern.

C10 contains a blocked PostCompact observation, but its required expected assertions are pointer/context recovery and reconstruction from canonical files/Git; the successful SessionStart trial directly demonstrates those assertions. No C10 change is included in this repair set.

## Repair invariants

1. qualification remains `workflow_dispatch` only from `main`;
2. self-hosted runner labels and Environment remain unchanged;
3. `approval=never` remains unchanged;
4. model-tool network access remains disabled;
5. no `danger-full-access`, approval/sandbox bypass, privileged container, or `SYS_ADMIN` is introduced;
6. project-hook trust bypass may only bypass the interactive hook-trust prompt;
7. every Git-mutating fixture is disposable and explicitly scoped;
8. evidence stores structural booleans/counts/hashes, not transcripts, credentials, private paths, or session/thread identifiers;
9. all six repaired capabilities use deterministic outer release-gate decisions;
10. no full/self-hosted qualification is run until hosted regression tests for this repair set are green.

## Exit criteria before the next full run

The repair PR may be merged only if hosted CI verifies the consolidated v6 ownership/delegation contract, fail-open external hook telemetry, deterministic C03 auxiliary Git-root setup, C06 isolated PreToolUse comparison, deterministic C16 diagnostic basis, valid materialized C01-C16 packages, absence of forbidden sandbox/container flags, and the existing cross-platform core/distribution checks.

Only after merge and green post-merge CI should a new `mode=full` qualification be dispatched.