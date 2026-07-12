# Validation, blind review, commit, and stop

## Deterministic validation

Before readiness, verify required files and schemas, canonical JSON, source-worktree immutability, planning-branch allowlist, ignored local state, instruction completeness, stable IDs, traceability, risk-control coverage, privacy, absence of placeholders, and agreement between JSON and Markdown.

## Blind review

Build a bundle containing only the original goal, bootstrap Git/lifecycle evidence, profiles, instruction map, immutable goal analysis, generated plan and stages, traceability, risks, and deterministic validator output.

Use a fresh read-only reviewer. Do not provide planner reasoning or self-review. The reviewer must assess completeness, contradictions, unsupported assumptions, rollback, testing, approvals, generator/executor separation, and critical traceability gaps.

Write `reports/plan-review/blind-review.md` and `.json` once. Hash both before comparison. Comparison writes separate output and never edits the blind review.

## Commit gate

Before commit, rerun profile, artifact, plan, diff, privacy, review, and comparison validation. Stage only allowlisted planning artifacts. Honor repository signing and hooks. Do not push unless separately requested and confirmed safe.

## Final report and hard stop

Report status, planning branch, commit SHA, plan path, assumptions, unknowns, review result, and the execution prompt.

Use the explicit statement: `No implementation was executed. Start a separate Codex run using the execution prompt in PLAN.md.`

Then stop.
