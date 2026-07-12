# Implementation Plan: {{TITLE}}

## Identity

- Plan ID: `{{PLAN_ID}}`
- Run ID: `{{RUN_ID}}`
- Contract: PlanAnvil 2.1
- Artifact schema: 1.1.0
- Base branch: `{{BASE_BRANCH}}`
- Base SHA: `{{BASE_SHA}}`
- Planning branch: `{{PLANNING_BRANCH}}`

## Original goal

{{GOAL}}

## Outcome and definition of done

{{OUTCOME_AND_DONE}}

## Generator stop boundary

PlanAnvil generated and validated this plan. It must not implement any stage, modify product code or tests, deploy, migrate, switch a live system, or integrate the base branch in this run.

## Separate execution-run prompt

Use this approved `PLAN.md` as the immutable execution contract in a separate Codex run. Reconcile `manifest.json`, `state.json`, `local-state.json`, the latest valid checkpoint, profiles, instruction map, and Git state before acting. Execute only the next approved action, preserve all gates and approvals, and stop on any mismatch.

## Scope

{{SCOPE}}

## Exclusions

{{EXCLUSIONS}}

## Assumptions, unknowns, and evidence

{{ASSUMPTIONS_UNKNOWNS_EVIDENCE}}

## Applicable instructions

{{INSTRUCTIONS}}

## System and change analysis

{{SYSTEM_ANALYSIS}}

## Dependencies and classification

{{DEPENDENCIES_AND_CLASSIFICATION}}

## Stable stage index

{{STAGE_INDEX}}

## Traceability

{{TRACEABILITY_SUMMARY}}

## Testing and independent verification

{{TESTING}}

## Git, integration, and control-root rules

{{GIT_AND_INTEGRATION}}

## Production verification, switching, and approvals

{{PRODUCTION_VERIFICATION}}

## Rollback and recovery

{{ROLLBACK_AND_RECOVERY}}

## Resume and reconciliation

{{RESUME}}

## Status and next action

- Status: `{{STATUS}}`
- Next action: `{{NEXT_ACTION}}`

## Final report requirements

{{FINAL_REPORT}}
