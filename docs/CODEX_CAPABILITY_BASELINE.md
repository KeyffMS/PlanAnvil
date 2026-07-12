# PlanAnvil — Codex Capability Baseline

> Verification date: 2026-07-12
> Tested model: `gpt-5.6-sol`
> Purpose: record reproducible runtime findings that affect PlanAnvil architecture.

This file records observed capability tests. It does not replace current official OpenAI documentation. Re-run critical tests when Codex behavior or configuration changes.

## Result summary

| ID | Result | Finding | PlanAnvil decision |
|---|---|---|---|
| C01 | PASS | Repository skill discovered from `.agents/skills`; legacy root `skills/` was not native-discovered | Use `.agents/skills/plan-anvil` |
| C02 | PASS | `allow_implicit_invocation: false` prevented implicit activation and allowed explicit `$skill` activation | Require explicit PlanAnvil activation |
| C03 | RUNTIME VARIANCE | Grandchild started despite a test configured with `max_depth = 1` | Do not treat `max_depth` as the sole topology control |
| C04 | PASS | Nested grandchild execution worked | Nesting is technically possible, but PlanAnvil contract remains flat |
| C05 | PASS | Fresh subagent read an untracked, uncommitted file | File handoffs work without commits; clean-worktree policy remains independent |
| C06 | PASS_STRONG with limitation | Path hook blocked five production-path write methods and allowed a test-path write; runtime reported `agent_type: default` | Use path hooks plus post-diff validation; do not trust agent type alone |
| C07 | PASS_STRONG | Hook blocked stash, reset, clean, wrappers, dynamic command construction, and an equivalent reset path in the tested set | Use Git allowlist hook as defense in depth, plus Git postcondition checks |
| C08 | PASS | `PreCompact` stopped manual compaction | Delay compaction until checkpoint when required |
| C09 | PASS with usability limitation | `PreCompact` stopped auto-compaction, but repeated blocking made the session unusable above threshold | Never create a permanent block loop; checkpoint then allow compact |
| C10 | PASS | `PostCompact` plus `SessionStart(compact)` restored a recovery pointer | Implement file-and-Git recovery after compact |
| C11 | PASS | Root session loaded root instructions; nested override loaded only when session CWD was in its scope | Explicitly map and hand off nested instructions |
| C12 | PASS | `project_doc_max_bytes` truncated automatic instruction loading | Hash, size, and explicitly read full instruction files |
| C13 | EXPECTED FAIL | `SubagentStart` ran but `continue: false` did not stop agent start | Use `SubagentStart` for audit and context only |
| C14 | PASS | Planning worktree and branch isolated planning artifacts and preserved source worktree | Require planning worktree isolation |
| C15 | PASS | Blind reviewer detected defect before implementer report; comparison detected false claims; blind report hash remained unchanged | Require immutable blind review then comparison |
| C16 | PASS with permission limitation | Plan-only prototype stopped after validation; `workspace-write` could not write `.git`, while higher permission mode created planning worktree safely | Run Git capability test and report permission requirement before planning |

## Architectural conclusions

### Native skill and activation

- Canonical path: `.agents/skills/plan-anvil/`.
- Implicit invocation must be disabled.
- Explicit `$plan-anvil` invocation remains available.

### Agent topology

- Codex can run nested agents.
- PlanAnvil nevertheless generates a flat direct-child topology under Jim.
- `agents.max_depth` is a configuration aid, not the sole enforcement mechanism.
- Actual agent-tree auditing is required before checkpoints.

### Hooks

- Hooks are useful and tested.
- `PreToolUse` is defense in depth, not a complete security boundary.
- `SubagentStart` cannot be used as a hard start blocker.
- Post-agent diff and Git-state validation remain mandatory.

### Git

- Ordinary workspace writes and `.git` metadata writes may have different permission outcomes.
- PlanAnvil must report Git capability before generating artifacts.
- Planning artifacts belong in an isolated planning worktree and branch.

### Instructions

- Nested instructions must be explicitly discovered for affected paths.
- Automatically loaded instructions may be truncated.
- Full instruction files must be explicitly read and hashed.

### Compaction

- Manual and automatic compaction can be delayed.
- Permanent blocking above the threshold is not viable.
- Required flow: checkpoint, allow compaction, recover pointer, reconcile from files and Git.

### Plan-only boundary

The tested prototype successfully:

- refused to implement product code;
- created only planning artifacts;
- used an isolated planning branch and worktree when Git permissions allowed;
- performed independent validation;
- stopped after validation.

This behavior is mandatory for the production skill.

## Evidence retention

The original capability-test repository contained:

```text
results/C01 ... results/C16
.codex/hooks/
.codex/agents/
tests/prompts/
```

The PlanAnvil repository should retain sanitized test prompts and expected outcomes, but must not commit session transcripts, private paths, credentials, or unrelated Git object databases.
