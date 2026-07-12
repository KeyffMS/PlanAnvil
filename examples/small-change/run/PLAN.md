# Implementation Plan: Display Name

## Identity

- Plan ID: `PG-20260712-180000-A1B2`
- Run ID: `20260712T180000Z_PG-20260712-180000-A1B2_display-name`
- Contract: PlanAnvil 2.1
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

## Production verification, switching, and approvals

Any live switch, irreversible action, or base-branch integration requires explicit user approval.

## Rollback and recovery

Each stage has a rollback boundary. Resume only after canonical files and Git reconcile.

## Resume and reconciliation

Read manifest, state, local state, profiles, analysis, instruction map, latest checkpoint, and Git state. Stop on mismatch.

## Status and next action

- Status: `PLAN_READY`
- Next action: `Start a separate execution run for STAGE-01.`

## Final report requirements

Report tests, verification, commits, remaining risks, and approvals. No implementation was executed. Start a separate Codex run using the execution prompt in PLAN.md.
