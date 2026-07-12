# Implementation Plan: Status History

## Identity

- Plan ID: `PG-20260712-180100-B2C3`
- Run ID: `20260712T180000Z_PG-20260712-180100-B2C3_status-history`
- Contract: PlanAnvil 2.1
- Artifact schema: 1.1.0
- Base branch: `main`
- Base SHA: `dedb6ab6843bf06d3ac7899aaf37923896915ee7`
- Planning branch: `pursue/plan/PG-20260712-180100-B2C3/status-history`

## Original goal

Replace a single status column with a status-history model without downtime.

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

Classification: `STATEFUL`. Component and state boundaries are defined by the stage briefs.

## Dependencies and classification

Dependencies are explicit and no stage may be skipped.

## Stable stage index

- `STAGE-01` — Add backward-compatible history storage.
- `STAGE-02` — Dual-write old and new status representations.
- `STAGE-03` — Backfill records with resumable checkpoints.
- `STAGE-04` — Switch reads after integrity verification.
- `STAGE-05` — Observe the switch and verify rollback viability.

## Traceability

REQ-01-01 → STAGE-01 → AC-01-01; REQ-02-01 → STAGE-02 → AC-02-01; REQ-03-01 → STAGE-03 → AC-03-01; REQ-04-01 → STAGE-04 → AC-04-01; REQ-05-01 → STAGE-05 → AC-05-01.

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
