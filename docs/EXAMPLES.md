# PlanAnvil — Contract Examples

These examples show expected decisions and artifact shapes. The implementation must later include complete golden fixtures under `examples/`.

## 1. Small isolated behavior change

### Request

```text
Add validation that rejects an empty display name.
```

### Repository evidence

- one validator module;
- existing unit-test suite;
- no public API shape change;
- no persistent-state change;
- clean Git state;
- profile status `VALID`.

### Expected PlanAnvil decision

```text
PLAN_READY
Risk: LOW
Stages: 1
```

### Stage outline

```text
STAGE-01
Outcome: Empty display names are rejected consistently.

Scope:
- validator behavior
- focused regression tests

Out of scope:
- renaming fields
- changing error transport
- UI copy changes

Acceptance:
- AC-01-01 empty string is rejected
- AC-01-02 whitespace-only input follows existing normalization policy
- AC-01-03 existing valid names remain accepted
```

PlanAnvil does not write the validator or tests. It only writes this contract and the later red/green test requirement.

## 2. Critical unknown blocks readiness

### Request

```text
Change account deletion so it permanently removes all user data.
```

### Missing evidence

- legal retention requirements;
- backup retention policy;
- downstream data consumers;
- definition of “all user data”;
- rollback or recovery expectations.

### Expected decision

```text
BLOCKED_BY_CRITICAL_UNKNOWN
```

The partial plan is retained.

PlanAnvil asks only the questions required to resolve:

- authoritative deletion scope;
- legally required retention;
- whether the operation is intentionally irreversible;
- approval owner for destructive execution.

It must not infer destructive policy from a broad user phrase.

## 3. Stateful backward-compatible change

### Request

```text
Replace a single status column with a status-history model without downtime.
```

### Expected classification

```text
Risk: HIGH
Classification: STATEFUL
```

### Expected stages

```text
STAGE-01  Add backward-compatible history storage
STAGE-02  Dual-write old and new representations
STAGE-03  Backfill historical records with resumable checkpoints
STAGE-04  Switch reads after integrity verification
STAGE-05  Observe and verify rollback viability
```

Destructive removal of the old column is excluded and assigned to a later plan.

Required controls include:

- verified recovery point;
- idempotent or checkpointed backfill;
- compatibility during switch;
- integrity counts;
- error and latency observation;
- explicit live-switch approval.

## 4. Git metadata write restriction

### Observation

- source worktree is clean;
- normal workspace files are writable;
- temporary ref or linked worktree creation is denied.

### Expected result

```text
BLOCKED_BY_GIT_PERMISSIONS
Git capability: GIT_WRITE_RESTRICTED
```

Allowed remediation text:

```text
Run Codex with a permission mode that permits Git metadata writes,
or manually create a planning branch and linked worktree and rerun PlanAnvil there.
```

PlanAnvil does not generate profile or plan artifacts before this blocker is resolved.

## 5. Detached HEAD with ambiguous base

### Observation

- `HEAD` is detached;
- multiple candidate branches contain the commit;
- no repository instruction identifies the intended base.

### Expected result

```text
BLOCKED_BY_GIT_STATE
Git capability: GIT_BASE_AMBIGUOUS
```

This requires a user decision because choosing the wrong base changes the implementation contract and integration target.

## 6. Hook unavailable but postconditions active

### Observation

- project is trusted;
- hooks are disabled in Codex configuration.

### Expected behavior

```text
Hook mode: HOOKS_DISABLED
Plan generation: permitted
Postcondition validation: mandatory
```

The final report must not claim that destructive commands or paths were hook-blocked.

## 7. Generator/executor boundary test

### Invalid generated instruction

```text
After creating PLAN.md, immediately start Jim and implement STAGE-01.
```

### Expected validator result

```text
PLAN_VALIDATION_FAILED
Finding: generator/executor boundary violation
```

A valid final section is:

```text
PlanAnvil has generated and validated the plan.
No implementation was executed.
Start a separate Codex run using the execution prompt in PLAN.md.
```

## 8. Minimal `manifest.json`

```json
{
  "schema_version": "1.0.0",
  "plan_id": "PG-20260712-143000-A1B2",
  "run_id": "20260712T143000Z_PG-20260712-143000-A1B2_display-name",
  "created_at": "2026-07-12T14:30:00Z",
  "generator_version": "0.1.0",
  "repository": {
    "root": "/repo",
    "fingerprint": "sha256:example",
    "base_branch": "main",
    "base_sha": "0000000000000000000000000000000000000000",
    "source_worktree": "/repo",
    "planning_branch": "pursue/plan/PG-20260712-143000-A1B2/display-name",
    "planning_worktree": "/worktrees/plan-anvil-display-name"
  },
  "paths": {
    "run_root": ".pursue/runs/20260712T143000Z_PG-20260712-143000-A1B2_display-name",
    "plan": "PLAN.md",
    "state": "state.json",
    "repository_profile": "../../SYSTEM_PROFILE.md",
    "local_profile": "../../SYSTEM_PROFILE.local.md"
  },
  "contract_versions": {
    "implementation_spec": "2.0",
    "plan_contract": "1.0.0",
    "artifact_schema": "1.0.0"
  }
}
```

The all-zero SHA is used only in this documentation example. Golden fixtures must use real fixture commits.

## 9. Required golden fixtures

Before release, the repository must contain complete generated outputs for:

```text
examples/small-change/
examples/stateful-change/
examples/blocked-plan/
examples/git-write-restricted/
```

Each fixture includes:

- request;
- fixture repository description or commit;
- expected status;
- `PLAN.md`;
- machine artifacts;
- deterministic validation result;
- blind review;
- comparison result;
- secret and path sanitization check.
