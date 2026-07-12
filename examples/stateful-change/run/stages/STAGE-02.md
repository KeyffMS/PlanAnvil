---
schema_version: "1.1.0"
stage_id: "STAGE-02"
outcome: 'Dual-write old and new status representations.'
classification: 'STATEFUL'
requirements: ['REQ-02-01']
criteria: ['AC-02-01']
risks: ['RISK-02-01']
dependencies: ['STAGE-01']
applicable_instructions: [{"path": "AGENTS.md", "sha256": "sha256:2222222222222222222222222222222222222222222222222222222222222222"}]
allowed_write_paths: ['src/status/**', 'tests/status/**']
---

# STAGE-02 — Dual-write old and new status representations.

## Outcome

Dual-write old and new status representations.

## Scope

Only the approved paths and acceptance behavior.

## Exclusions

Unrelated changes and automatic integration.

## Affected paths or discovery procedure

Verify the mapped paths before editing.

## Applicable instructions

Read the hashed instruction file in full.

## Dependencies and conflicts

Dependencies: STAGE-01. Stop on conflict.

## Acceptance criteria

AC-02-01 must pass.

## Risks and controls

RISK-02-01 is controlled by the linked controls and evidence.

## Evidence cycle

GREEN BASELINE → EXPECTED RED → IMPLEMENTATION → FULL GREEN → INDEPENDENT VERIFICATION.

## Modifier and verifier roles

One modifier writes approved paths; the verifier remains read-only.

## Commit and checkpoint

Create one coherent commit and `CHECKPOINT-02-VERIFIED`.

## Rollback

Revert the stage commit or apply the stage-specific recovery procedure.
