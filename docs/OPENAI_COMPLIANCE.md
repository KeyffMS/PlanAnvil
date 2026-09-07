# PlanAnvil — OpenAI Codex Compliance Record

> **Original contract review:** 2026-07-12; scoped recovery/source review: 2026-09-05; live qualification: 2026-09-06
> **Scope:** contract 2.1; baseline 2.3 qualification of the 0.2.0 release candidate
> **Rule:** current official OpenAI documentation is authoritative for Codex behavior.

## 1. Official sources

| Area | Official source | Contract decision |
|---|---|---|
| Skills | https://developers.openai.com/codex/skills/ | Use `.agents/skills/plan-anvil/`; disable implicit invocation |
| Hooks | https://developers.openai.com/codex/hooks/ | Project hooks require trusted active configuration and remain optional defense in depth |
| Subagents | https://developers.openai.com/codex/subagents/ | Project agents live in `.codex/agents/`; enforce flat direct-child topology in the generated contract, not a runtime depth setting |
| Project instructions | https://developers.openai.com/codex/guides/agents-md/ | Map overrides, standard files, configured fallbacks, precedence and size limits |
| Configuration | https://developers.openai.com/codex/config-reference/ | Validate every used key and supported value |
| Git worktrees | https://developers.openai.com/codex/environments/git-worktrees/ | Worktrees isolate checked-out files while sharing Git metadata |
| Sandboxing and approvals | https://developers.openai.com/codex/sandbox/ | Verify actual Git capabilities instead of inferring them from workspace access |
| GPT-5.6 guidance | https://developers.openai.com/api/docs/guides/prompt-guidance-gpt-5p6 | Keep prompts explicit, scoped and evidence-driven |

Redirects from `developers.openai.com` to current official OpenAI documentation remain valid official sources.

## 2. Active Codex decisions

### 2.1 Skill location and activation

Canonical skill path:

```text
.agents/skills/plan-anvil/
```

Required metadata:

```yaml
policy:
  allow_implicit_invocation: false
```

PlanAnvil activates only through an explicit request such as `$plan-anvil`.

### 2.2 Hooks

Project hooks may be defined in `<repo>/.codex/hooks.json` or active project configuration. Project trust is required.

`PreToolUse` covers supported paths but not every equivalent operation. `SubagentStart` may add context but is not a startup blocker.

Hooks are optional. Deterministic filesystem and Git postconditions remain mandatory in every hook mode.

For JSON definitions, the Windows override is `commandWindows`. TOML may use `command_windows` or `commandWindows` according to current documentation.

### 2.3 Custom agents and topology

Project custom agents live under `.codex/agents/`.

The generated execution contract requires a flat direct-child topology and does not rely on undocumented `agents.max_depth`. Current agent enablement/concurrency settings are distinct from the deterministic topology requirement.

Authorized technical agents are direct children of the executor. Actual agent evidence is checked as an additional correctness control.

Custom planning agents are optional. The core generator must still support equivalent fresh read-only analysis and review roles when project agent profiles are unavailable.

### 2.4 Project instructions

PlanAnvil maps:

- `AGENTS.override.md`;
- `AGENTS.md`;
- configured fallback names;
- directory scope and precedence;
- configured instruction-byte limits.

Complete files are explicitly read and hashed. Automatically loaded context is not assumed complete.

### 2.5 Worktrees and Git permissions

Linked worktrees isolate checked-out files and share Git metadata.

PlanAnvil performs a safe reversible probe for refs, branches, linked worktrees, index updates, a real commit and cleanup.

A commit check cannot be skipped while returning `GIT_READY`. Signing and hook failures have explicit blocker results.

### 2.6 Recovery delivery correction — verified 2026-09-05

This scoped review targets Codex CLI `0.153.4`; it does not re-date the entire older compliance review above or claim new live capability evidence.

The [official hooks documentation](https://developers.openai.com/codex/hooks/) specifies that `PostCompact` accepts common output fields, not model-visible `additionalContext`. `SessionStart` matches `source`, including `compact`, and supplies additional developer context before the next model request after compaction, including automatic compaction inside a turn.

Pinned source confirmation:

- [hooks/events/compact.rs](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/hooks/src/events/compact.rs): `StatelessHookOutcome` and the compact output parser expose control/events, not additional contexts.
- [core/hook_runtime.rs](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/core/src/hook_runtime.rs): `run_post_compact_hooks` emits events without recording additional context; `run_pending_session_start_hooks` records the supported context.
- [config/loader/mod.rs](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/config/src/loader/mod.rs): linked-worktree hook declarations are resolved from the corresponding primary checkout.

PlanAnvil now emits a universal readiness advisory for PostCompact and supplies the actual pointer/next-action context from SessionStart. The after-compaction qualification narrows SessionStart to `^compact$` in an independent fixture, excluding ordinary startup as a source of the opaque proof. It retains exact echo, checkpoint, source-immutability and tool restrictions. The two C10 acceptance assertion strings remain unchanged; the earlier description claiming two context-injection events was incorrect and is superseded.

See `CODEX_RECOVERY_DELIVERY_AUDIT_2026-09-05.md` for the implementation and regression coverage. Offline tests are not live evidence.

## 3. Current architecture decisions

### 3.1 Generator and executor separation

PlanAnvil implements only plan generation and validation.

Jim, Jenny, implementation agents, task branches, integration branches and live verification exist only in a generated contract for a separate run.

### 3.2 Lifecycle order

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

### 3.3 Control-root ownership

The retained planning worktree is the durable control root.

The later executor writes state, checkpoints, reports and evidence there. It modifies product code and tests only in task or integration worktrees.

Execution-control artifacts may be committed to the planning branch. Product-code commits may not.

### 3.4 Local-path privacy

Committed artifacts contain no absolute local paths, usernames or local service locations.

Machine-specific locators are stored only in ignored files:

```text
.pursue/SYSTEM_PROFILE.local.md
.pursue/runs/<RUN-ID>/local-state.json
```

Committed `manifest.json` uses repository-relative paths and Git identity only.

### 3.5 Canonical state

Committed machine state is versioned JSON. Human-readable contracts and reports remain Markdown.

Canonical files are validated against shipped JSON Schemas and updated atomically.

## 4. Unsupported active behaviors

The implementation does not claim:

- that hooks intercept every write path;
- that `SubagentStart` blocks startup;
- that untrusted project hooks execute;
- that custom-agent labels alone enforce permissions;
- that PlanAnvil can elevate its sandbox or Git permissions;
- that every worktree begins on an attached branch;
- that conversational state is durable;
- that compaction may be blocked indefinitely;
- that the generator may execute the generated plan in the same run;
- that PlanAnvil integrates with Superpowers.

Unsupported behavior is absent rather than simulated or marked partially supported.

## 5. Required compatibility review

Before each release:

1. review every official source above;
2. record the verification date;
3. record tested Codex versions and model slugs;
4. rerun release-gating capability tests;
5. validate every used config key and hook field;
6. update or remove behavior inconsistent with current documentation;
7. verify local-path privacy and ignored-state rules;
8. ensure no active contradiction remains.

A relevant documentation change blocks release until the affected record and tests are reviewed.

## 6. Compliance checklist

- [x] Native repository skill path specified
- [x] Implicit invocation disabled
- [x] Generator and executor boundary explicit
- [x] Project hook location and trust documented
- [x] Hooks and custom agents explicitly optional
- [x] Hook limitations documented
- [x] Windows hook override names documented
- [x] `SubagentStart` treated as context and audit only
- [x] Flat topology is enforced by the generated contract without assuming a runtime depth setting
- [x] Instruction precedence and truncation documented
- [x] Complete Git commit capability is tested rather than assumed
- [x] Planning worktree defined as durable control root
- [x] Product and control artifact ownership separated
- [x] Committed artifacts exclude local absolute paths
- [x] Local profile and local state are ignored
- [x] Machine-state formats defined
- [x] Unsupported behaviors excluded from the active contract
- [x] Complete source-scoped live C01–C16 evidence committed for run #25
- [ ] Finite C08 repaired-path completion verified live and committed for production closure

## 7. Source-scoped qualification and release closure — 2026-09-07

Run `34060321283` reproduced all baseline 2.3 capabilities with Codex CLI `0.153.4`, model `gpt-5.6-sol`, Debian 13, at PlanAnvil `d0384f76bc4150d33bb8f51ef5981f3243b3cfb3`. The archived result retains its original source identifier and hashes. Current status and remaining constraints are in `QUALIFICATION_STATUS.md`; earlier audits are historical, not current blockers by default.

C10 delivers recovery through `SessionStart(source=compact)`; `PostCompact` remains advisory. C13's project-native agent and hook pass via the allowed non-ephemeral retry, not an unrestricted home-scoped replacement. C08's historical positive trial timed out after proving unblocking. The stricter finite C08 follow-up has not yet produced live evidence and remains a production-publication prerequisite.

The C08 fixture now isolates the deliberate invalid-checkpoint trigger from ordinary startup recovery by narrowing SessionStart to `^compact$` in the disposable root checkout before bootstrap. It does not change product hook behavior. Repaired recovery still runs through the real compact source. A correct stop is an expected terminal failure of the negative CLI invocation, whereas the positive invocation must complete normally. No timeout is accepted as completed repair.
