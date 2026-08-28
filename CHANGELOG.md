# Changelog

All notable changes to PlanAnvil are documented here.

## [Unreleased]

### Fixed

- canonicalize event repository paths before active-run routing so source-worktree matching is stable across macOS symlink aliases and Windows path aliases;
- keep checkpoint recovery assertions platform-neutral by comparing canonical paths;
- update the artifact-sealing lock regression test to observe the current `validate_plan_contract` gate;
- make the Git-hook probe fixture emit explicit hook diagnostics while preserving fail-closed classification for unrelated commit failures;
- synchronize golden blind-review fixtures and dependent comparison hashes with the required independent `plan-anvil-reviewer` author role.

## [0.1.0] - 2026-07-12

### Added

- concise repository skill with explicit-only activation;
- deterministic Python 3.11 generator utilities;
- read-only source preflight and complete reversible Git capability probe;
- isolated planning branch and linked-worktree creation;
- repository and local profiling, freshness hashes, instruction mapping with critical-conflict blocking, and run scaffolding;
- durable Git-capability and lifecycle bootstrap evidence plus immutable goal analysis;
- versioned JSON Schemas, canonical state transitions, privacy checks, and atomic writes;
- plan, stage, diff, artifact, source-immutability, and traceability validation;
- immutable blind-review bundle, recording, and comparison workflow;
- planning-only commit gate and observable final stop;
- optional read-only Codex agents and defense-in-depth hooks;
- unit, integration, boundary, privacy, freshness, schema-traversal, and hook tests;
- golden contract examples and capability-evidence scaffolding.

### Release status

The deterministic core is implemented. Production readiness remains gated on reproduced Codex capability evidence defined in `docs/CODEX_CAPABILITY_BASELINE.md`.
