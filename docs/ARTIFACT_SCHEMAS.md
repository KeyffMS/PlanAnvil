# PlanAnvil — Artifact Schemas

> Canonical machine state is JSON. Markdown is used for human-readable contracts and narrative reports.  
> The implementation MUST ship actual JSON Schema files under `.agents/skills/plan-anvil/schemas/`.

## 1. General conventions

All canonical JSON documents MUST:

- use UTF-8;
- use schema version `1.0.0` for the first implementation;
- use RFC 3339 UTC timestamps;
- use SHA-256 hashes written as lowercase hexadecimal;
- reject unknown required-enum values;
- permit forward-compatible optional fields only when the schema explicitly allows them;
- end with a newline;
- be written atomically.

Common identifier formats:

```text
Plan:       PG-YYYYMMDD-HHMMSS-XXXX
Run:        YYYYMMDDTHHMMSSZ_<PLAN-ID>_<slug>
Stage:      STAGE-01, STAGE-02, STAGE-03A
Requirement: REQ-03-01
Criterion:  AC-03-01
Risk:       RISK-03-01
Control:    CTRL-03-01
Checkpoint: CHECKPOINT-03-VERIFIED
```

Deleted identifiers are never reused.

## 2. `manifest.json`

Purpose: immutable run identity and path map. It is created once and may only receive additive, version-compatible metadata before the first checkpoint.

Required shape:

```json
{
  "schema_version": "1.0.0",
  "plan_id": "PG-20260712-143000-A1B2",
  "run_id": "20260712T143000Z_PG-20260712-143000-A1B2_example",
  "created_at": "2026-07-12T14:30:00Z",
  "generator_version": "0.1.0",
  "repository": {
    "root": "/absolute/source/repository",
    "fingerprint": "sha256:...",
    "base_branch": "main",
    "base_sha": "40-hex-sha",
    "source_worktree": "/absolute/source/repository",
    "planning_branch": "pursue/plan/PG-20260712-143000-A1B2/example",
    "planning_worktree": "/absolute/planning/worktree"
  },
  "paths": {
    "run_root": ".pursue/runs/20260712T143000Z_PG-20260712-143000-A1B2_example",
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

Validation rules:

- paths under `paths` are relative to `run_root` unless explicitly documented otherwise;
- source and planning worktrees must be distinct;
- base SHA must exist in the repository;
- planning branch must point to a commit descended from base SHA;
- repository fingerprint is derived from stable repository identity, not only a local path.

## 3. `state.json`

Purpose: current generator or later execution state.

Required shape:

```json
{
  "schema_version": "1.0.0",
  "revision": 7,
  "updated_at": "2026-07-12T14:42:00Z",
  "mode": "PLAN_GENERATION",
  "status": "ARTIFACTS_GENERATED",
  "current_stage": null,
  "current_phase": "DETERMINISTIC_VALIDATION",
  "next_action": {
    "type": "RUN_VALIDATOR",
    "target": "PLAN.md"
  },
  "last_checkpoint": null,
  "open_blockers": [],
  "artifact_hashes": {
    "PLAN.md": "sha256:..."
  }
}
```

`mode` values:

```text
PLAN_GENERATION
PLAN_EXECUTION
```

Generator `status` values:

```text
NEW
SOURCE_PREFLIGHT_PASSED
GIT_READY
PLANNING_WORKTREE_READY
PROFILE_READY
INSTRUCTION_MAP_READY
ANALYSIS_READY
ARTIFACTS_GENERATED
DETERMINISTICALLY_VALID
BLIND_REVIEW_WRITTEN
COMPARISON_VALID
PLAN_COMMITTED
STOPPED
BLOCKED
FAILED
```

Rules:

- `revision` increments by exactly one per accepted update;
- `next_action` contains exactly one action;
- terminal states use `next_action.type = "NONE"`;
- `artifact_hashes` must match files before a transition;
- a stale revision update is rejected.

## 4. `compliance.json`

Purpose: run-specific compatibility and enforcement record.

Required shape:

```json
{
  "schema_version": "1.0.0",
  "verified_at": "2026-07-12T14:35:00Z",
  "codex": {
    "version": "unknown",
    "model": "gpt-5.6-sol",
    "permission_mode": "default",
    "project_trust": "TRUSTED",
    "hook_mode": "HOOKS_TRUSTED"
  },
  "capabilities": [
    {
      "id": "CAP-SKILL-DISCOVERY",
      "status": "VERIFIED",
      "evidence": ["reports/validation/skill-discovery.json"]
    }
  ],
  "unsupported": [],
  "warnings": []
}
```

Allowed evidence statuses:

```text
VERIFIED
DOCUMENTED
OBSERVED_UNREPRODUCED
CONTRADICTED
UNKNOWN
NOT_APPLICABLE
```

A `CONTRADICTED` item that affects active behavior blocks `PLAN_READY`.

## 5. `traceability.json`

Required shape:

```json
{
  "schema_version": "1.0.0",
  "requirements": [
    {
      "id": "REQ-01-01",
      "text": "The endpoint rejects unauthenticated requests.",
      "stages": ["STAGE-01"],
      "criteria": ["AC-01-01"]
    }
  ],
  "criteria": [
    {
      "id": "AC-01-01",
      "stage": "STAGE-01",
      "risks": ["RISK-01-01"],
      "controls": ["CTRL-01-01"],
      "evidence_type": "AUTOMATED_TEST"
    }
  ],
  "gaps": []
}
```

Gap types:

```text
UNCOVERED_REQUIREMENT
STAGE_WITHOUT_REQUIREMENT
CRITERION_WITHOUT_EVIDENCE
RISK_WITHOUT_CONTROL
CONTROL_WITHOUT_BEHAVIOR
PUBLIC_BEHAVIOR_WITHOUT_REQUIRED_APPROVAL
```

Any critical gap blocks readiness.

## 6. Risk files

Each `risks/RISK-*.json` contains:

```json
{
  "schema_version": "1.0.0",
  "id": "RISK-03-01",
  "stage": "STAGE-03",
  "level": "HIGH",
  "description": "Migration may leave old and new records inconsistent.",
  "source": "Repository analysis",
  "affected_components": ["database", "worker"],
  "probability": "MEDIUM",
  "impact": "HIGH",
  "detection": ["CTRL-03-02"],
  "criteria": ["AC-03-01"],
  "controls": ["CTRL-03-01", "CTRL-03-02"],
  "mitigation": "Use resumable expand-and-migrate flow.",
  "rollback": "Restore verified recovery point before switch.",
  "status": "OPEN"
}
```

Allowed levels:

```text
LOW
MEDIUM
HIGH
```

Allowed statuses:

```text
OPEN
MITIGATED
ACCEPTED_BY_USER
CLOSED
REALIZED
```

Only the user may accept an otherwise-unmitigated high risk when policy permits acceptance.

## 7. Checkpoint files

A checkpoint is immutable after creation.

```json
{
  "schema_version": "1.0.0",
  "id": "CHECKPOINT-03-VERIFIED",
  "created_at": "2026-07-12T17:00:00Z",
  "mode": "PLAN_EXECUTION",
  "stage": "STAGE-03",
  "phase": "VERIFICATION",
  "result": "PASS",
  "git": {
    "branch": "pursue/PG-.../example",
    "head": "40-hex-sha",
    "worktree": "/absolute/task/worktree",
    "status": "CLEAN"
  },
  "tests": {
    "summary": "42 passed, 0 failed",
    "evidence": ["tests/results/STAGE-03.json"]
  },
  "risks": {
    "open": [],
    "closed": ["RISK-03-01"]
  },
  "agent_tree": {
    "status": "COMPLIANT",
    "evidence": ["reports/validation/agent-tree-STAGE-03.json"]
  },
  "write_scope": {
    "status": "COMPLIANT",
    "evidence": ["diffs/STAGE-03.json"]
  },
  "next_action": {
    "type": "BEGIN_STAGE",
    "target": "STAGE-04"
  },
  "recovery": [
    "Read manifest.json",
    "Read state.json",
    "Verify this checkpoint hash",
    "Reconcile Git state"
  ],
  "artifact_hashes": {}
}
```

Checkpoint `result` values:

```text
PASS
FAIL
BLOCKED
```

A checkpoint is valid only when its Git and artifact evidence still matches.

## 8. Execution lock

Canonical path:

```text
run-root/.execution-lock
```

The lock is created with exclusive-create semantics and contains:

```json
{
  "schema_version": "1.0.0",
  "run_id": "...",
  "owner": {
    "hostname": "host",
    "pid": 1234,
    "session_id": "optional"
  },
  "created_at": "2026-07-12T15:00:00Z",
  "heartbeat_at": "2026-07-12T15:02:00Z",
  "command": "plan-anvil-execute"
}
```

The generator uses an equivalent `.generation-lock`.

A lock cannot be broken automatically merely because its timestamp is old. Owner liveness and session evidence must also be checked.

## 9. Reports

Narrative reports are Markdown. Each report has a JSON metadata sidecar with the same basename.

Example:

```text
reports/plan-review/blind-review.md
reports/plan-review/blind-review.json
```

Metadata contains:

```json
{
  "schema_version": "1.0.0",
  "report_type": "BLIND_PLAN_REVIEW",
  "created_at": "2026-07-12T14:50:00Z",
  "author_role": "plan-anvil-reviewer",
  "inputs": {
    "PLAN.md": "sha256:..."
  },
  "result": "FAIL",
  "findings": [
    {
      "id": "FINDING-01",
      "severity": "HIGH",
      "summary": "Rollback is undefined for the migration stage."
    }
  ],
  "markdown_hash": "sha256:..."
}
```

The comparison phase must verify `markdown_hash` and must not rewrite either blind-review file.

## 10. Stage briefs

Stage briefs remain Markdown because they are execution contracts.

Every file begins with a deterministic metadata block:

```yaml
---
schema_version: "1.0.0"
stage_id: "STAGE-03"
outcome: "Migrate existing records without downtime."
classification: "STATEFUL"
requirements: ["REQ-03-01"]
criteria: ["AC-03-01", "AC-03-02"]
risks: ["RISK-03-01"]
dependencies: ["STAGE-02"]
applicable_instructions:
  - path: "AGENTS.md"
    sha256: "..."
allowed_write_paths:
  - "src/migration/**"
  - "tests/migration/**"
---
```

The implementation may use a minimal internal YAML parser only for this restricted frontmatter grammar, or it may generate a JSON sidecar. It must not add a general YAML runtime dependency to the core scripts.

## 11. Atomic update protocol

For every mutable canonical JSON file:

1. read and schema-validate the current file;
2. verify expected revision or expected hash;
3. construct the complete new document;
4. write `<name>.tmp.<RUN-ID>` in the same directory;
5. flush and fsync;
6. replace atomically;
7. fsync the directory where supported;
8. reread and validate;
9. remove no prior checkpoint or evidence.

On Windows, use an atomic replacement mechanism supported by Python for the same filesystem and fail explicitly when antivirus or file locking prevents replacement.

## 12. Path safety

Before any write:

- resolve the candidate path;
- reject traversal outside the approved root;
- reject symlink escapes;
- compare case-normalized paths on case-insensitive filesystems;
- reject writes through repository submodules unless explicitly in scope;
- reject `.git` paths except through dedicated Git commands;
- record the approved glob and resolved path.

Allowed-path matching is performed on repository-relative POSIX-style paths after safe resolution.

## 13. Schema evolution

Schema changes follow semantic versioning.

- patch: clarification that does not change accepted documents;
- minor: backward-compatible optional fields;
- major: incompatible field or semantic change.

A run keeps the schema version with which it was created. Migration of existing run state is explicit, reversible where possible, and never automatic across a major version.
