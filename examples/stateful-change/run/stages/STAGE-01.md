---
schema_version: "1.1.0"
stage_id: "STAGE-01"
outcome: 'Add backward-compatible history storage.'
classification: 'STATEFUL'
requirements: ['REQ-01-01']
criteria: ['AC-01-01']
risks: ['RISK-01-01']
dependencies: []
applicable_instructions: [{"path": "AGENTS.md", "sha256": "sha256:2222222222222222222222222222222222222222222222222222222222222222"}]
allowed_write_paths: ['src/models/**', 'migrations/**', 'tests/migrations/**']
---

# STAGE-01 — Add backward-compatible history storage.

## Outcome

Add backward-compatible history storage.

## Scope

Only the approved paths and acceptance behavior.

## Exclusions

Unrelated changes and automatic integration.

## Affected paths or discovery procedure

Verify the mapped paths before editing.

## Applicable instructions

Read the hashed instruction file in full.

## Dependencies and conflicts

Dependencies: none. Stop on conflict.

## Acceptance criteria

AC-01-01 must pass.

## Risks and controls

RISK-01-01 is controlled by the linked controls and evidence.

## Evidence cycle

GREEN BASELINE → EXPECTED RED → IMPLEMENTATION → FULL GREEN → INDEPENDENT VERIFICATION.

## Modifier and verifier roles

One modifier writes approved paths; the verifier remains read-only.

## Commit and checkpoint

Create one coherent commit and `CHECKPOINT-01-VERIFIED`.

## Rollback

Revert the stage commit or apply the stage-specific recovery procedure.
