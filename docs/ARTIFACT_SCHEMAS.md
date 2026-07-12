# PlanAnvil — Artifact Schemas

> Canonical machine state is JSON. Markdown is used for human-readable contracts and narrative reports.  
> The implementation MUST ship matching JSON Schema files under `.agents/skills/plan-anvil/schemas/`.

## 1. General conventions

All canonical JSON documents MUST:

- use UTF-8 and LF line endings;
- use schema version `1.0.0` for the first implementation;
- use RFC 3339 UTC timestamps;
- use SHA-256 hashes as lowercase hexadecimal prefixed with `sha256:`;
- reject unknown enum values;
- reject unspecified fields unless a schema explicitly permits them;
- end with a newline;
- be written atomically.

Identifier formats:

```text
Plan:        PG-YYYYMMDD-HHMMSS-XXXX
Run:         YYYYMMDDTHHMMSSZ_<PLAN-ID>_<slug>
Stage:       STAGE-01, STAGE-02, STAGE-03A
Requirement: REQ-03-01
Criterion:   AC-03-01
Risk:        RISK-03-01
Control:     CTRL-03-01
Checkpoint:  CHECKPOINT-03-VERIFIED
```

Deleted identifiers are never reused.

## 2. `manifest.json`

Purpose: immutable run identity and path map.

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

- source and planning worktrees are distinct;
- `base_sha` exists in the repository;
- the planning branch descends from `base_sha`;
- the repository fingerprint uses stable repository identity, not only a local path;
- paths are resolved and checked against their documented root.

## 3. `state.json`

Purpose: current generator or later execution state.

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

Allowed `mode` values:

```text
PLAN_GENERATION
PLAN_EXECUTION
```

Generator states:

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

- `revision` increments by exactly one for every accepted update;
- `next_action` contains exactly one action;
- terminal states use `next_action.type = "NONE"`;
- artifact hashes must match before a transition;
- stale revision updates are rejected.

## 4. `compliance.json`

Purpose: current run-specific compatibility and enforcement record.

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

Allowed capability statuses:

```text
VERIFIED
DOCUMENTED
FAILED
BLOCKED
UNKNOWN
NOT_APPLICABLE
```

A `FAILED`, `BLOCKED` or `UNKNOWN` capability that is required by active behavior blocks `PLAN_READY`.

The file records only current requirements and current run results. It is not an archive of superseded observations.

## 5. `traceability.json`

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
  "mitigation": "Use a resumable expand-and-migrate flow.",
  "rollback": "Restore the verified recovery point before switching.",
  "status": "OPEN"
}
```

Risk levels:

```text
LOW
MEDIUM
HIGH
```

Risk statuses:

```text
OPEN
MITIGATED
ACCEPTED_BY_USER
CLOSED
REALIZED
```

Only the user may accept an otherwise unmitigated high risk when policy permits acceptance.

## 7. Checkpoints

Checkpoint files are immutable after creation.

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

Checkpoint results:

```text
PASS
FAIL
BLOCKED
```

A checkpoint is valid only while its Git and artifact evidence still matches.

## 8. Generation and execution locks

Canonical paths:

```text
run-root/.generation-lock
run-root/.execution-lock
```

Each lock is created with exclusive-create semantics and contains:

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
  "command": "plan-anvil"
}
```

A lock cannot be removed automatically merely because its timestamp is old. Owner liveness or session evidence must also show that it is inactive.

## 9. Reports

Narrative reports are Markdown. Each has a JSON metadata sidecar with the same basename.

```text
reports/plan-review/blind-review.md
reports/plan-review/blind-review.json
```

Example sidecar:

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

The comparison phase verifies `markdown_hash` and never rewrites the blind-review files.

## 10. Stage briefs

Stage briefs remain Markdown and begin with deterministic metadata:

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

The implementation may use a restricted internal parser for this exact frontmatter grammar or a JSON sidecar. The core scripts must not add a general YAML runtime dependency.

## 11. Atomic update protocol

For every mutable canonical JSON file:

1. read and schema-validate the current file;
2. verify the expected revision or hash;
3. construct the complete replacement document;
4. write a sibling temporary file;
5. flush and fsync;
6. replace atomically;
7. fsync the containing directory where supported;
8. reread and validate;
9. retain immutable checkpoints and evidence.

On Windows, use an atomic replacement mechanism supported by Python on the same filesystem and fail explicitly when file locking prevents replacement.

## 12. Path safety

Before every write:

- resolve the candidate path;
- reject traversal outside the approved root;
- reject symlink escapes;
- normalize case on case-insensitive filesystems;
- reject submodule writes unless explicitly in scope;
- reject direct `.git` writes outside dedicated Git commands;
- record the approved rule and resolved path.

Allowed-path matching uses repository-relative POSIX-style paths after safe resolution.

## 13. Schema evolution

Schema versions follow semantic versioning:

- patch: clarification that does not change accepted documents;
- minor: backward-compatible optional fields;
- major: incompatible field or semantic change.

A run retains the schema version with which it was created. Major-version migration is explicit and never automatic.