# Generator lifecycle

Authority order: current official OpenAI Codex documentation, `docs/IMPLEMENTATION_SPEC.md`, architecture, artifact schemas, compliance record, capability baseline, examples.

## Mandatory state order

`SOURCE_PREFLIGHT → GIT_CAPABILITY_CHECK → CREATE_PLANNING_BRANCH_AND_WORKTREE → CREATE_OR_VALIDATE_PROFILES → DISCOVER_INSTRUCTIONS → ANALYZE_GOAL → GENERATE_ARTIFACTS → DETERMINISTIC_VALIDATION → BLIND_PLAN_REVIEW → COMPARISON_AND_FINAL_VALIDATION → COMMIT_PLANNING_ARTIFACTS → REPORT_AND_STOP`

No state may be skipped. Bootstrap transitions are preserved in `evidence/lifecycle.json`; the complete successful Git probe is preserved in `evidence/git-capability.json`. Both are schema-validated and hashed into canonical state before instruction mapping.

## Source preflight

The source worktree is read-only. Verify Git, repository root, `HEAD`, cleanliness, conflicts, active Git operations, branch/base identity, and linked worktrees. Preflight must not create files, refs, branches, commits, or repository-local temporary directories.

## Git capability probe

Use an external temporary directory and unique probe names. Verify temporary refs, a branch, linked worktree, file creation, index update, a real commit under current identity/signing/hooks policy, cleanup, and unchanged source branch, `HEAD`, index, and files.

A commit check is mandatory for `GIT_READY`. Return a precise blocker for identity, signing, hooks, permissions, worktree support, dirty state, active operations, or ambiguous detached `HEAD`.

## Planning isolation

Create `pursue/plan/<PLAN-ID>/<slug>` from the verified base and retain an external linked planning worktree. The source remains unchanged. All profiles and run artifacts are created only after this worktree exists.

The planning worktree is the durable control root. It may contain only `.pursue/SYSTEM_PROFILE.md`, required ignore rules, generated plan/control/evidence artifacts, and plan-specific documentation. Product implementation and product tests are forbidden.

## Blocking statuses

- `BLOCKED_BY_GIT_STATE`
- `BLOCKED_BY_GIT_PERMISSIONS`
- `BLOCKED_BY_RUNTIME_PREREQUISITE`
- `BLOCKED_BY_INSTRUCTION_CONFLICT`
- `BLOCKED_BY_CRITICAL_UNKNOWN`
- `PLAN_VALIDATION_FAILED`

Preserve evidence and describe safe remediation. Never hide failures with destructive Git commands.
