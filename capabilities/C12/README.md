# C12 — project_doc_max_bytes truncation

- Source: `DOCUMENTED`
- Release-gating: `yes`
- Current result: `REPRODUCED`
- Qualification package state: `READY_FOR_LIVE_RUN`
- Prepared: `2026-08-28`

## Objective

Use a deliberately oversized instruction fixture with a small project_doc_max_bytes setting and compare automatic loading with PlanAnvil explicit full-file hashing.

## Live metadata to record

Before changing this result to `REPRODUCED`, record the exact Codex version, model slug, OS, permission mode, project trust, fixture commit, setup/cleanup, sanitized observations, evaluation, and hashes. Do not commit transcripts, credentials, private paths, or unrelated repository data.

## Execution

Use `fixture/`, `config/README.md`, `prompt.txt`, and `run-command.txt`. Replace the current BLOCKED `actual.sanitized.json`/`evaluation.json` with the live result, update `capabilities/index.json`, then run `python tools/rehash_capability.py C12` and `python tools/validate_capabilities.py`.

## Live qualification

- Date: `2026-09-07`
- Codex: `codex-cli 0.153.4`
- Model: `gpt-5.6-sol`
- OS: `Debian GNU/Linux 13 (trixie)`
- Permission mode: `approval=never; sandbox=per-trial; model-tool network disabled`
- Project trust: `trusted via CLI override for disposable fixture repositories`
- Source commit: `a9cdcdc1e0cad70e88b60869e75e4166046dd306`
- Result: `REPRODUCED`
