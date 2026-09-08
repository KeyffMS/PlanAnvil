# C13 — SubagentStart context semantics

- Source: `DOCUMENTED_AND_SOURCE_VERIFIED`
- Release-gating: `yes`
- Current result: `REPRODUCED`
- Qualification package state: `READY_FOR_LIVE_RUN`
- Prepared: `2026-09-05`
- Baseline: `2.3`
- Target runtime: Codex CLI `0.153.4`; record the exact executed version

## Objective

Verify real project-scoped `SubagentStart` context injection and the documented non-blocking meaning of `continue=false`, separately from the known ephemeral parent-thread failure and from errors in the qualification proxy process.

Codex matches `SubagentStart` handlers against the spawned `agent_type`. The qualification child must therefore be spawned with `agent_type` exactly `fixture_agent`; a default or unnamed child is not equivalent.

## Baseline 2.3 transport

The v7 live harness attempts the explicitly declared project-scoped `fixture_agent` through `codex exec --ephemeral` first. Only the recognized `collab spawn failed: no thread with id` failure may activate a controlled non-ephemeral retry. That retry uses a separate disposable repository containing both the project-scoped agent and the project-scoped hook. Its disposable `CODEX_HOME` supplies persisted project trust and isolated runtime persistence, not a substitute agent or hook.

`REPRODUCED` requires one real project-scoped `SubagentStart`, `additionalContext`, a child echo of an outer-generated proof absent from the root prompt, unchanged repository state, verified session cleanup, and unchanged authentication metadata. `continue=false` is recorded as a compatibility signal but is not expected to stop `SubagentStart`.

The generated qualification proxy command must pass both required arguments: `SubagentStart subagent-start-fixture.py`. Offline process tests verify this contract but never constitute live capability evidence.

## Live metadata to record

Record the exact Codex version, model slug, OS, permission mode, persisted project trust, fixture commit, transport used, exact requested `agent_type`, setup/cleanup, sanitized observations, evaluation, and hashes. Do not commit transcripts, credentials, private paths, proof values, session IDs, or unrelated repository data.

## Live qualification

- Date: `2026-09-07`
- Codex: `codex-cli 0.153.4`
- Model: `gpt-5.6-sol`
- OS: `Debian GNU/Linux 13 (trixie)`
- Permission mode: `approval=never; sandbox=per-trial; model-tool network disabled`
- Project trust: `trusted via CLI override for disposable fixture repositories`
- Source commit: `a9cdcdc1e0cad70e88b60869e75e4166046dd306`
- Result: `REPRODUCED`
