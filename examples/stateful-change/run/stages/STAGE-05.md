---
schema_version: "1.1.0"
stage_id: "STAGE-05"
outcome: 'Observe the switch and verify rollback viability.'
classification: 'STATEFUL'
requirements: ['REQ-05-01']
criteria: ['AC-05-01']
risks: ['RISK-05-01']
dependencies: ['STAGE-04']
applicable_instructions: [{"path": "AGENTS.md", "sha256": "sha256:2222222222222222222222222222222222222222222222222222222222222222"}]
allowed_write_paths: ['ops/verification/**', 'tests/integration/**']
---

# STAGE-05 — Observe the switch and verify rollback viability.

## Outcome

Observe the switch and verify rollback viability.

## Scope

Only the approved paths and acceptance behavior.

## Exclusions

Unrelated changes and automatic integration.

## Affected paths or discovery procedure

Verify the mapped paths before editing.

## Applicable instructions

Read the hashed instruction file in full.

## Dependencies and conflicts

Dependencies: STAGE-04. Stop on conflict.

## Acceptance criteria

AC-05-01 must pass.

## Risks and controls

RISK-05-01 is controlled by the linked controls and evidence.

## Evidence cycle

GREEN BASELINE → EXPECTED RED → IMPLEMENTATION → FULL GREEN → INDEPENDENT VERIFICATION.

## Modifier and verifier roles

One modifier writes approved paths; the verifier remains read-only.

## Commit and checkpoint

Create one coherent commit and `CHECKPOINT-05-VERIFIED`.

## Rollback

Revert the stage commit or apply the stage-specific recovery procedure.
