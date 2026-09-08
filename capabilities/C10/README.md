# C10 — Recovery context through SessionStart

- Source: `DOCUMENTED_AND_SOURCE_VERIFIED`
- Release-gating: `yes`
- Current result: `REPRODUCED`
- Qualification package state: `READY_FOR_LIVE_RUN`
- Target runtime: Codex CLI `0.153.4`; record the executed version

Verify file/Git-based recovery at startup and immediately after genuine automatic compaction. The model-visible channel is SessionStart(source=compact), not PostCompact.additionalContext. PostCompact reports readiness using universal output fields. Canonical files/Git remain authoritative.

The two acceptance assertions remain unchanged. Exact opaque echo, actual lifecycle execution, no unauthorized tool reads, valid checkpoints, and source/planning immutability are mandatory. A declared model PASS without exact echo is not evidence of delivery.

## Live qualification

- Date: `2026-09-07`
- Codex: `codex-cli 0.153.4`
- Model: `gpt-5.6-sol`
- OS: `Debian GNU/Linux 13 (trixie)`
- Permission mode: `approval=never; sandbox=per-trial; model-tool network disabled`
- Project trust: `trusted via CLI override for disposable fixture repositories`
- Source commit: `a9cdcdc1e0cad70e88b60869e75e4166046dd306`
- Result: `REPRODUCED`
