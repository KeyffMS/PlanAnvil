# Codex CLI 0.152 compatibility contract

PlanAnvil targets the runtime semantics of Codex CLI 0.152.x. These rules are product requirements, not qualification-only exceptions.

## Tool mutation boundary

Codex 0.152 exposes `apply_patch` through model metadata as a freeform tool, and the native `PreToolUse` hook adapter is attached to that freeform handler. PlanAnvil must not assume that every file-change transport observed by the client is intercepted by `PreToolUse`.

During PlanAnvil generation, hook enforcement is an early guard only. The deterministic planning-diff/source-immutability validator is authoritative. After any direct file-change tool call that is not performed by a PlanAnvil deterministic script, immediately run `validate_diff.py --no-write-report` for the active run. On any out-of-policy path or source-worktree change, stop the run; do not continue planning or review.

Prefer the PlanAnvil deterministic scripts for control-state writes. Never use a successful file-change item or missing hook event as evidence that a mutation was safe.

## Compaction

`model_auto_compact_token_limit` is not necessarily the effective trigger. Codex 0.152 can add the token-budget fallback buffer before declaring the auto-compaction limit reached. PlanAnvil therefore treats `PreCompact`/`PostCompact` as runtime lifecycle events and never assumes they fire at an exact raw token count.

Normal product operation must not disable a user's TokenBudget configuration merely to force compaction. Qualification may disable the fallback buffer only in an isolated fixture whose purpose is to deterministically exercise the real automatic-compaction path.

## Subagents

`SubagentStart` matcher input is the spawned `agent_type`. PlanAnvil must spawn configured roles with the exact role name, not as an unnamed/default child:

- `plan_anvil_profiler`
- `plan_anvil_reviewer`

The role name must match the `name` field in the corresponding agent TOML and the project `SubagentStart` matcher.

For Codex 0.152, `SubagentStart` may inject `additionalContext`, but `continue: false` is not a stop control for this event. PlanAnvil must never depend on `continue: false` to prevent the child from starting.

## Fail-closed rule

When the active Codex runtime cannot provide a lifecycle behavior required by the PlanAnvil contract, preserve deterministic evidence and stop with a runtime prerequisite blocker. Do not weaken path, source-immutability, approval, or recovery guarantees to make the run pass.
