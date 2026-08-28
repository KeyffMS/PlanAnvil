# Codex capability qualification — 2026-08-28

## Outcome

A sequential C01–C16 qualification attempt was performed after restoring green CI on `main`.

- Deterministic baseline: GitHub Actions run #24 on commit `acb1dd664d039ed6d8b3069b6e7c24be7646e559` passed all 64 tests on Ubuntu, macOS and Windows.
- Documentation baseline: current official OpenAI Codex documentation was reviewed on 2026-08-28.
- Live Codex runtime: **BLOCKED**. The available execution environment has no `codex` executable and no authenticated Codex runtime exposed through the available connectors.
- Release decision: **NO-GO**. No capability is labeled `REPRODUCED` without its required committed sanitized live evidence package.

## Sequential results

| ID | Docs/contract check | Deterministic support | Live result | Notes |
|---|---|---|---|---|
| C01 | PASS — current docs scan repository `.agents/skills` from CWD toward repository root | repository layout present | BLOCKED | Requires live skill discovery evidence |
| C02 | PASS — current docs define `allow_implicit_invocation: false` as disabling implicit invocation while preserving explicit `$skill` | `test_skill_metadata_requires_explicit_activation` PASS | BLOCKED | Requires implicit-vs-explicit runtime prompts |
| C03 | BASELINE DRIFT CORRECTED — current docs do not document `agents.max_depth` | execution-contract flat topology validation PASS; legacy-depth-only acceptance removed | BLOCKED | Requires live agent event-tree evidence consistent with flat PlanAnvil contract |
| C04 | PASS — current docs expose subagent enablement/concurrency, not a nesting-depth knob | n/a; nested descendants are not part of PlanAnvil execution contract | BLOCKED | Informational/non-gating in baseline 2.2 |
| C05 | CONTRACT PASS — review bundle is explicit, immutable and hash-bound | review integrity and immutable write tests PASS | BLOCKED | Mandatory reviewer handoff still needs live Codex evidence |
| C06 | PASS — docs confirm supported local function-tool coverage and explicit exceptions | hook guard tests PASS | BLOCKED | Needs live supported and non-intercepted tool-path evidence |
| C07 | CONTRACT PASS | destructive Git and hook-diagnostic tests PASS | BLOCKED | Needs committed capability package |
| C08 | PASS — docs confirm `PreCompact` can stop before compaction | checkpoint-required hook test PASS | BLOCKED | Needs live manual/auto compaction evidence |
| C09 | CONTRACT PASS | valid checkpoint allows compaction test PASS | BLOCKED | Needs live no-loop compaction/recovery evidence |
| C10 | PASS — docs confirm `PostCompact` and `SessionStart` context outputs | recovery hook behavior covered by tests | BLOCKED | Needs live post-compaction continuation evidence |
| C11 | PASS — docs confirm root-to-CWD scope, override/fallback precedence and merge order | instruction map/conflict tests PASS | BLOCKED | Needs live instruction-source evidence |
| C12 | PASS — docs define `project_doc_max_bytes` as instruction-chain size limit | explicit hash/freshness tests PASS | BLOCKED | Needs live truncation fixture |
| C13 | PASS — docs confirm `SubagentStart` context and that `continue: false` does not stop startup | hook implementation compiles/tests | BLOCKED | Needs live subagent start evidence |
| C14 | CONTRACT PASS | planning worktree isolation and source preservation tests PASS | BLOCKED | Needs committed capability package |
| C15 | CONTRACT PASS | tamper, immutable blind review and independent author-role tests PASS | BLOCKED | Needs live reviewer run with seeded defects |
| C16 | CONTRACT PASS | reversible Git probe, cleanup and hook classification tests PASS | BLOCKED | Needs live matrix under supported Codex permission modes |

## Documentation checked

- `https://developers.openai.com/codex/skills`
- `https://developers.openai.com/codex/config-reference`
- `https://developers.openai.com/codex/subagents`
- `https://developers.openai.com/codex/hooks`
- `https://developers.openai.com/codex/guides/agents-md`

## Baseline correction

Baseline 2.1 relied on `agents.max_depth = 1`. Current Codex documentation no longer documents that setting. It documents `agents.enabled` and `agents.max_concurrent_threads_per_session`; `agents.max_threads` remains only a legacy concurrency alias.

PlanAnvil 2.2 therefore:

1. uses the canonical concurrency setting;
2. does not claim runtime depth enforcement;
3. requires generated execution contracts to state an explicit flat direct-child topology;
4. rejects a plan that relies only on the legacy `agents.max_depth = 1` phrase.

## Remaining release blocker

Run the live C01–C03 and C05–C16 fixtures in an authenticated current Codex runtime and commit the complete sanitized evidence package for every required capability. Only then may `capabilities/index.json` move those entries from `BLOCKED` to `REPRODUCED`.
