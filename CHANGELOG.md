# Changelog

All notable changes to PlanAnvil are documented here.

## [Unreleased]

### Added

- add a controlled `workflow_dispatch`-only Codex qualification workflow for the trusted `plananvil-codex` self-hosted runner;
- add a sequential C01-C16 live qualification controller that creates disposable fixture repositories, runs fresh ephemeral Codex trials, sanitizes structural evidence, rehashes/validates each package, and exports evidence only as a GitHub Actions artifact;
- add regression tests ensuring the live qualification controller redacts private-looking data and never disables the Codex sandbox/approval boundary.

### Changed

- update pinned `actions/checkout` and `actions/setup-python` workflow SHAs to the current v7 releases while retaining immutable action pinning and Node 24 compatibility;
- require the full Linux Codex qualification job to pass a system-`bubblewrap` user-namespace probe before C01-C16, so incompatible Podman runners fail fast instead of timing out capability-by-capability;
- update the qualification evidence uploader to the Node-24-native `actions/upload-artifact` v6 immutable SHA;
- require production releases to use a GitHub-verified signed annotated tag whose target is reachable from `main`;
- fail the production release gate closed when the release worktree is dirty or Git cleanliness cannot be verified;
- document the controlled self-hosted Codex qualification path and keep the previous sandbox procedure as a manual fallback.

## [0.2.0] - 2026-08-28

### Added

- standard-library repository distribution manager with install, verify, upgrade, status and uninstall operations;
- transactional rollback, ownership/hash state, conservative Codex config merging, and structural hook merging;
- distribution tests covering clean repositories, existing `AGENTS.md`, existing `.codex/config.toml`, unrelated hooks, upgrade conflicts and uninstall conflicts;
- deterministic release archive builder, candidate/production release gate, and tag-driven GitHub Release workflow;
- deterministic C01-C16 qualification template archive containing fixture, prompt, config, expected result, current sanitized BLOCKED result, evaluation and SHA-256 manifests;
- capability evidence materializer/validator/rehash tools and a live Codex sandbox runbook;
- installation, troubleshooting, and release documentation.

### Changed

- refresh the Codex capability baseline to 2.2 against current 2026-08-28 official documentation;
- replace legacy agent concurrency/depth configuration with `agents.enabled` and `agents.max_concurrent_threads_per_session`;
- enforce flat direct-child execution topology in the generated contract instead of relying on undocumented `agents.max_depth` behavior;
- record the 2026-08-28 C01–C16 qualification attempt and its live Codex runtime blocker;
- pin GitHub Actions to immutable SHAs and Node-24-based checkout/setup-python releases;
- expand CI across Python 3.11 and the current upper supported interpreter on Ubuntu, macOS and Windows;
- split distribution/release-candidate validation into a stable named CI check.

### Fixed

- canonicalize event repository paths before active-run routing so source-worktree matching is stable across macOS symlink aliases and Windows path aliases;
- keep checkpoint recovery assertions platform-neutral by comparing canonical paths;
- update the artifact-sealing lock regression test to observe the current `validate_plan_contract` gate;
- make the Git-hook probe fixture emit explicit hook diagnostics while preserving fail-closed classification for unrelated commit failures;
- synchronize golden blind-review fixtures and dependent comparison hashes with the required independent `plan-anvil-reviewer` author role.

### Release status

0.2.0 is code-complete as a release candidate. Production publication remains blocked until protected-`main` administration is enabled and required C01-C16 live Codex evidence is committed as `REPRODUCED`.

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

The deterministic core was implemented. Production readiness remained gated on reproduced Codex capability evidence.
