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
- use deterministic live-qualification harness setup for C01, C05, C09, and C14 so repository-skill discovery, stale handoff rejection, genuine auto-compaction, and writable auxiliary Git isolation are actually exercised;
- extend deterministic live qualification for C02, C09, C11, C13, C14, and C16 with explicit-only skill policy, current AGENTS precedence evidence, project-scoped SubagentStart semantics, bytecode-free PlanAnvil bootstrap, and real Git signing/hook failure diagnostics;
- make C12 a deterministic runtime byte-budget probe with redundant `project_doc_max_bytes` enforcement, secret head/tail markers, zero-tool automatic-loading evidence, and outer PlanAnvil full-file hash verification;
- make C06, C08, and C09 deterministic live probes using the real PlanAnvil PreToolUse/PreCompact/PostCompact hooks, explicit postcondition evidence, low-limit `body_after_prefix` auto-compaction triggers, checkpoint repair, repeated compaction, and post-second-compaction continuation checks;
- retain diagnostic-only historical C13 controllers; the active full controller uses the baseline 2.3 ephemeral-first, known-error-gated fallback described below;
- promote C13 qualification to baseline 2.3: full qualification remains ephemeral-first but may use a known-error-gated non-ephemeral retry with a project-scoped, explicitly declared `fixture_agent` and project-scoped `SubagentStart` hook; disposable `CODEX_HOME` isolates only trust/auth bridging and persistence and cleanup/auth invariants remain fail-closed;
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

### Qualification closure — 2026-09-07

- preserve complete baseline 2.3 live evidence from full run #25, `34060321283`, tested at `d0384f76bc4150d33bb8f51ef5981f3243b3cfb3` with Codex CLI 0.153.4, `gpt-5.6-sol`, Debian 13; all C01–C16 were reproduced;
- retain the exact source-bound archive, hashes and original limitations; C13 passed via the permitted project-native non-ephemeral fallback;
- replace the old C08 repaired-path workload with a finite pressure/finish scenario and strict termination checks; the old positive timeout remains in historical evidence and the replacement still requires live confirmation;
- add C08-only qualification and real-CLI loopback conformance without changing C09/C10/C13 runtime behavior, product payload or live runner security;
- reset newly materialized template indices to unexecuted package results instead of inheriting historical success labels;
- validate qualification archive integrity and qualified product identity, and require committed finite C08 completion evidence before production publication.

### Release status

0.2.0 remains a release candidate. Full baseline qualification is recorded; production publication awaits the finite C08 live follow-up, strict release validation and a verified signed annotated tag. No tag or release has been published by the qualification-closure change.

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
