# PlanAnvil — OpenAI Codex Compliance Record

> **Verification date:** 2026-07-12  
> **Scope:** current documentation contract for the first production-ready PlanAnvil implementation  
> **Rule:** only current official OpenAI documentation is authoritative for Codex behavior.

## 1. Official sources

| Area | Official source | Contract decision |
|---|---|---|
| Skills | https://developers.openai.com/codex/skills/ | Use `.agents/skills/plan-anvil/`; disable implicit invocation |
| Hooks | https://developers.openai.com/codex/hooks/ | Project hooks require active trusted `.codex` configuration and remain defense in depth |
| Subagents | https://developers.openai.com/codex/subagents/ | Project agents live in `.codex/agents/`; depth `1` is the flat-topology setting |
| Project instructions | https://developers.openai.com/codex/guides/agents-md/ | Map overrides, standard files, configured fallbacks, precedence and size limits |
| Configuration | https://developers.openai.com/codex/config-reference/ | Validate every used key and supported value |
| Git worktrees | https://developers.openai.com/codex/environments/git-worktrees/ | Worktrees share Git metadata and isolate checked-out files |
| Sandboxing and approvals | https://developers.openai.com/codex/sandbox/ | Verify actual Git capabilities instead of inferring them from workspace access |
| GPT-5.6 guidance | https://developers.openai.com/api/docs/guides/prompt-guidance-gpt-5p6 | Keep prompts explicit, scoped and evidence-driven |

Redirects from `developers.openai.com` to current official OpenAI documentation remain valid official sources.

## 2. Active Codex decisions

### 2.1 Skill location and activation

The canonical skill path is:

```text
.agents/skills/plan-anvil/
```

The skill metadata contains:

```yaml
policy:
  allow_implicit_invocation: false
```

PlanAnvil activates only through an explicit request such as `$plan-anvil`.

### 2.2 Hooks

Project hooks may be defined in `<repo>/.codex/hooks.json` or the active project configuration. Project trust is required.

`PreToolUse` covers supported tool paths but not every equivalent operation. `SubagentStart` may add context but is not a startup blocker.

PlanAnvil therefore treats hooks as optional defense in depth. Deterministic filesystem and Git postconditions remain mandatory in every hook mode.

### 2.3 Custom agents and topology

Project custom agents live under `.codex/agents/` and define their current documented fields.

The generated execution contract uses:

```text
agents.max_depth = 1
```

All authorized technical agents are direct children of the executor. Actual agent evidence is checked as an additional correctness control.

### 2.4 Project instructions

PlanAnvil maps:

- `AGENTS.override.md`;
- `AGENTS.md`;
- configured fallback names;
- directory scope and precedence;
- configured instruction-byte limits.

Complete instruction files are explicitly read and hashed. Automatically loaded context is not assumed complete.

### 2.5 Worktrees and Git permissions

Linked worktrees isolate checked-out files while sharing Git metadata.

PlanAnvil performs a safe reversible probe for the operations it actually requires: refs, branches, linked worktrees, index updates, commits and cleanup. It does not infer `.git` write access from ordinary workspace writes.

## 3. Current architecture decisions

### 3.1 Generator and executor separation

PlanAnvil implements only plan generation and validation.

Jim, Jenny, implementation agents, task branches, integration branches and live verification exist only in the generated execution contract for a separate run.

Planning-time profiler and reviewer agents have separate names, permissions and responsibilities.

### 3.2 Lifecycle order

The required order is:

```text
source preflight
→ Git capability probe
→ planning branch and worktree
→ profiles
→ instruction mapping
→ goal analysis
→ plan generation
→ deterministic validation
→ blind review
→ comparison
→ planning commit
→ stop
```

Profiles and plan artifacts are written only inside the planning worktree. The source worktree remains unchanged.

### 3.3 Canonical state

Machine state is versioned JSON. Human-readable contracts and reports remain Markdown.

Canonical files are validated against shipped JSON Schemas and updated atomically.

### 3.4 Complete Git probe

`GIT_READY` requires successful verification of every Git operation used by the generator. A temporary-ref check alone is insufficient.

Identity, signing, repository hooks, worktree support, base resolution and cleanup failures have distinct blocking results.

## 4. Unsupported active behaviors

The implementation does not claim:

- that hooks intercept every write path;
- that `SubagentStart` blocks startup;
- that untrusted project hooks execute;
- that custom-agent labels alone enforce permissions;
- that PlanAnvil can elevate its own sandbox or Git permissions;
- that every worktree begins on an attached branch;
- that conversational state is durable;
- that compaction may be blocked indefinitely;
- that the generator may execute the generated plan in the same run;
- that PlanAnvil integrates with Superpowers.

Unsupported behavior is absent from the active contract rather than simulated or marked partially supported.

## 5. Required compatibility review

Before each release:

1. review every official source above;
2. record the verification date;
3. record the tested Codex version and model slugs;
4. rerun release-gating capability tests;
5. validate every used config key and hook field;
6. update or remove behavior inconsistent with current documentation;
7. ensure no active contradiction remains.

A relevant change in official documentation blocks release until the affected record and tests are reviewed.

## 6. Compliance checklist

- [x] Native repository skill path specified
- [x] Implicit invocation disabled
- [x] Generator/executor boundary explicit
- [x] Project hook location and trust documented
- [x] Hook limitations documented
- [x] `SubagentStart` treated as context and audit only
- [x] Project custom-agent location documented
- [x] Flat topology uses current documented depth behavior
- [x] Instruction precedence and truncation documented
- [x] Git capability is tested rather than assumed
- [x] Machine-state formats defined
- [x] Unsupported behaviors excluded from the active contract
- [ ] Production implementation and committed capability fixtures completed
