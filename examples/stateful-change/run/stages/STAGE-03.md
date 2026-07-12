---
schema_version: "1.1.0"
stage_id: "STAGE-03"
outcome: 'Backfill records with resumable checkpoints.'
classification: 'STATEFUL'
requirements: ['REQ-03-01']
criteria: ['AC-03-01']
risks: ['RISK-03-01']
dependencies: ['STAGE-02']
applicable_instructions: [{"path": "AGENTS.md", "sha256": "sha256:2222222222222222222222222222222222222222222222222222222222222222"}]
allowed_write_paths: ['scripts/backfill/**', 'tests/backfill/**']
---

# STAGE-03 — Backfill records with resumable checkpoints.

## Outcome

Backfill records with resumable checkpoints.

## Scope

Only the approved paths and acceptance behavior.

## Exclusions

Unrelated changes and automatic integration.

## Affected paths or discovery procedure

Verify the mapped paths before editing.

## Applicable instructions

Read the hashed instruction file in full.

## Dependencies and conflicts

Dependencies: STAGE-02. Stop on conflict.

## Acceptance criteria

AC-03-01 must pass.

## Risks and controls

RISK-03-01 is controlled by the linked controls and evidence.

## Evidence cycle

GREEN BASELINE → EXPECTED RED → IMPLEMENTATION → FULL GREEN → INDEPENDENT VERIFICATION.

## Modifier and verifier roles

One modifier writes approved paths; the verifier remains read-only.

## Commit and checkpoint

Create one coherent commit and `CHECKPOINT-03-VERIFIED`.

## Rollback

Revert the stage commit or apply the stage-specific recovery procedure.
