# Qualification execution-boundary audit — 2026-09-05

## Scope and authority

Audited PlanAnvil source: `7b6322e4c2b11d4b78b5be714c94b88644fb6147`.
Observed live run: [qualification #21](https://github.com/KeyffMS/PlanAnvil/actions/runs/33968031850), Codex CLI `0.153.4`, explicit model `gpt-5.6-sol`.

The implementation specification, generator/executor separation, product hooks, approval policy, sandbox, source immutability, baseline 2.3 and all `expected.json` assertions remain unchanged. This patch repairs qualification machinery, not the meaning of the product capabilities. Offline tests are not live evidence.

## Source-verified contracts

- [Official hooks documentation](https://developers.openai.com/codex/hooks): project/user hook sources, context output and event-specific control effects.
- [Pinned config loader](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/config/src/loader/mod.rs): `root_checkout_hooks_folder_for_dir` and `merge_root_checkout_project_hooks` select root-checkout hook declarations for linked worktrees. Ordinary worktree-local config is distinct from hook-declaration provenance.
- [Pinned hook discovery](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/hooks/src/engine/discovery.rs): uses each layer's `hooks_config_folder()`; hook sources can be additive.
- [Pinned hook execution](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/hooks/src/engine/command_runner.rs): executes commands with the event cwd, which is not necessarily the directory containing the declarations.
- [Pinned startup semantics](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/hooks/src/events/session_start.rs): SubagentStart matches `agent_type`, injects context and does not use `continue:false` as a startup stop.

## Defect, repair and executable regression

### C13 process contract

The active compatibility context substituted a generic proxy requiring event and script arguments while the project fixture generated a command with neither argument. The proxy raised `IndexError` before executing the actual hook or recording telemetry. Zero recorder entries did not prove missing project-hook discovery.

Repair: pass `SubagentStart subagent-start-fixture.py` to the existing generated command. The agent and hook remain project-scoped, with explicit `fixture_agent`, and the recognized-error-only ephemeral fallback is unchanged.

Regression: enter the real compatibility context, seed the same declared project fixture as v7, execute the actual configured command in a repository with spaces, and assert exit code, context JSON, continue=false, one telemetry record and unchanged Git state. No Codex process or model is involved in this process-contract test.

### C10 configuration provenance

The previous PostCompact probe removed SessionStart only from a linked planning worktree. Codex still loaded the primary checkout's declarations. The same proof could reach the model through SessionStart, invalidating attribution to PostCompact.

Repair: independent source repositories, planning worktrees and random proofs for the two trials. Prepare the second root checkout's hook selection before the fixture commit, product bootstrap and checkpoint. Verify root/local declarations agree and preserve both source and planning state during the probe. Keep the actual product recovery and compaction scripts; never synthesize a live hook event in the qualification runtime.

Regression: the offline driver substitutes only Codex. It executes the real installer, Git operations, product start/checkpoint/validator and generated hook processes, using root-checkout declarations and planning cwd. It checks independent roots/proofs, valid checkpoints, context delivery and no proof retention. The driver models the pinned loader rule; it is not a substitute for live confirmation of that rule.

### C09 successful completion

Run #21 recorded 31 PreCompact and 30 PostCompact events and a Codex invocation timeout. The old evaluator could nevertheless classify the trial REPRODUCED.

Repair: require successful invocation completion and a positive structured C09 result in addition to the existing two-cycle, checkpoint and continuation assertions. A timeout or missing result is BLOCKED, never a pass. Partial lifecycle observations remain visible. C08's intentional negative stop trial is not changed.

Regression: call the actual C09 evaluator with controlled observations; two cycles cannot conceal a timeout or absent completion payload. Completed positive evidence still passes; a missing continuation or observed stop still prevents reproduction.

This patch does not guess a new auto-compaction threshold. C09 may still time out live; that would now be accurately reported rather than converted into a green result. Repeated compaction under the artificially low fixture limit is not, by itself, proof of a product loop.

## Red-to-green verification

The test-only commit `f25fb15e4664a7afab371f696eae71dedd8876fe` added executable regressions before repairs. [Hosted CI #102](https://github.com/KeyffMS/PlanAnvil/actions/runs/33976076211) ran 134 distribution/harness tests and reported exactly four failures: C13 argv, C10 root-source isolation, C09 timeout and C09 missing output. Existing tests did not detect those defects.

The same regressions remain in the patched suite. CI additionally executes qualification boundary tests on Linux, macOS and Windows with Python 3.11 and 3.14. The POSIX platforms execute the exact generated shell command; Windows checks the equivalent generated Python argv contract. The actual controlled live runner is Linux.

## Targeted runner handoff

Use the existing allowed workflow `PlanAnvil Codex qualification`, branch `main`, mode `recovery`. It selects C09, C10 and C13 using the same v7 capability runtimes as `full`; it does not use the separate precision fixtures.

The targeted summary explicitly declares `scope`, `diagnostic_only=true`, `selected_gate_passed` and `release_gate_passed=false`. The full index still considers every required capability. A targeted success cannot release the product or substitute for a final C01–C16 run.

No hosted test needs runner credentials, and this change does not dispatch a self-hosted run. No claim is made that the upstream ephemeral parent-thread failure is fixed. Live qualification remains necessary after offline verification.
