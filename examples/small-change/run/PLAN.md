# Implementation Plan: Display Name

## Identity

- Plan ID: `PG-20260712-180000-A1B2`
- Run ID: `20260712T180000Z_PG-20260712-180000-A1B2_display-name`
- Contract: PlanAnvil 2.3
- Artifact schema: 1.1.0
- Base branch: `main`
- Base SHA: `dedb6ab6843bf06d3ac7899aaf37923896915ee7`
- Planning branch: `pursue/plan/PG-20260712-180000-A1B2/display-name`

## Original goal

Add validation that rejects an empty display name.

## Outcome and definition of done

Every acceptance criterion is proven and the later executor can stop or roll back safely.

## Generator stop boundary

PlanAnvil generates and validates this contract only. It does not modify product code or tests and does not execute a stage.

## Separate execution-run prompt

In a separate Codex run, load this plan and canonical state, reconcile Git and the latest checkpoint, then execute only the next approved stage.

## Execution runtime invariants

Use a flat direct-child topology. Jim coordinates and never modifies product code or tests. Jenny owns approved tests only. One implementation agent modifies approved product paths. The independent verifier remains read-only. Winston Wolfe performs read-only incident analysis only after six implementation failures.

Only one agent modifies repository files at a time. After every file-changing tool call, verify the actual changed paths against the approved stage scope before another mutation; `PreToolUse` is an early guard, not the sole mutation boundary.

Use STRATEGY-A with ATTEMPT-A1, ATTEMPT-A2, and ATTEMPT-A3. If that strategy is exhausted, use materially different STRATEGY-B with ATTEMPT-B1, ATTEMPT-B2, and ATTEMPT-B3. After six implementation failures, stop for Winston Wolfe analysis.

## Scope

The stage briefs define the complete approved scope.

## Exclusions

Automatic base-branch integration, unrelated refactors, and unapproved destructive work are excluded.

## Assumptions, unknowns, and evidence

The analysis files contain verified assumptions and no critical unknowns.

## Applicable instructions

Read and verify the complete hashed instruction map before any later write.

## System and change analysis

Classification: `ISOLATED`. Component and state boundaries are defined by the stage briefs.

## Dependencies and classification

Dependencies are explicit and no stage may be skipped.

## Stable stage index

- `STAGE-01` — Reject empty display names while preserving valid input.

## Traceability

REQ-01-01 → STAGE-01 → AC-01-01.

## Testing and independent verification

Behavior stages require GREEN BASELINE → EXPECTED RED → IMPLEMENTATION → FULL GREEN → INDEPENDENT VERIFICATION.

## Git, integration, and control-root rules

Product changes occur only in task or integration worktrees. The planning worktree remains the control root. One modifier acts at a time.

- Task branch: `pursue/PG-20260712-180000-A1B2/display-name`
- Integration branch: `pursue/integration/PG-20260712-180000-A1B2/display-name`

## Production verification, switching, and approvals

Explicit user approval is required before any base merge or push, any live switching or environment/service switch, and every irreversible operation.

## Rollback and recovery

Each stage has a rollback boundary. Resume only after canonical files and Git reconcile. Compaction recovery uses observed lifecycle events and canonical checkpoint/Git state rather than an assumed token count.

## Resume and reconciliation

Read manifest, state, local state, profiles, analysis, instruction map, latest checkpoint, and Git state. Stop on mismatch.

## Status and next action

- Status: `PLAN_READY`
- Next action: `Start a separate execution run for STAGE-01.`

## Final report requirements

Report tests, verification, commits, remaining risks, and approvals. No implementation was executed. Start a separate Codex run using the execution prompt in PLAN.md.
