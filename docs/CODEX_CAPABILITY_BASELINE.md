# PlanAnvil — Codex Capability Baseline

> **Baseline version:** 2.3  
> **Review date:** 2026-09-02  
> **Purpose:** define current expected Codex behavior and reproducible release tests.  
> **Authority:** current official OpenAI documentation has precedence.

## 1. Evidence model

Expected behavior uses one source:

```text
DOCUMENTED
CONTRACT_DEFINED
```

Test execution uses one result:

```text
NOT_RUN
REPRODUCED
FAILED
BLOCKED
```

`DOCUMENTED` means current official OpenAI documentation defines the expected behavior.

`CONTRACT_DEFINED` means the behavior is enforced by PlanAnvil's deterministic implementation.

`REPRODUCED` requires a committed, sanitized evidence package. Informal observations, documentation review alone, deterministic unit tests alone, and remembered runtime behavior are not sufficient live Codex evidence.

## 2. Required evidence package

Each reproduced test directory contains:

```text
CXX/
├── README.md
├── fixture/
├── prompt.txt
├── config/
├── run-command.txt
├── expected.json
├── actual.sanitized.json
├── evaluation.json
└── hashes.json
```

The README records the test objective, date, Codex version, model, operating system, permission mode, fixture commit, setup, cleanup and sanitization.

Do not commit session transcripts, credentials, private paths, unrelated Git databases or user data.

## 3. Current capability matrix

| ID | Expected behavior | Source | Evidence | Contract decision |
|---|---|---|---|---|
| C01 | Repository skills are discovered from `.agents/skills` | DOCUMENTED | BLOCKED | Use `.agents/skills/plan-anvil` |
| C02 | `allow_implicit_invocation: false` disables implicit invocation while explicit `$skill` invocation remains available | DOCUMENTED | BLOCKED | Require explicit `$plan-anvil` activation |
| C03 | Generated execution contracts require an explicit flat direct-child topology and do not rely on a Codex nesting-depth setting | CONTRACT_DEFINED | BLOCKED | Enforce flat topology deterministically in `PLAN.md` validation |
| C04 | Codex subagent workflows are controlled by current `[agents]` enablement/concurrency settings; PlanAnvil does not require nested descendants | DOCUMENTED | BLOCKED | Keep generated execution deliberately flat |
| C05 | Required reviewer handoffs use explicit immutable files and hashes | CONTRACT_DEFINED | BLOCKED | Reject missing, stale or out-of-root review inputs |
| C06 | `PreToolUse` covers supported local function-tool paths but not every equivalent path | DOCUMENTED | BLOCKED | Hooks plus mandatory postcondition validation |
| C07 | The Git guard rejects the configured unsafe-command corpus | CONTRACT_DEFINED | BLOCKED | Git postconditions remain mandatory |
| C08 | `PreCompact` can stop compaction | DOCUMENTED | BLOCKED | Delay only until a valid checkpoint exists |
| C09 | Compaction is allowed after checkpoint creation without a permanent stop loop | CONTRACT_DEFINED | BLOCKED | Checkpoint, allow, recover and reconcile |
| C10 | `PostCompact` and `SessionStart` can provide recovery context | DOCUMENTED | BLOCKED | Inject only a recovery pointer |
| C11 | Project instructions follow documented directory scope and precedence | DOCUMENTED | BLOCKED | Explicitly map affected instructions |
| C12 | `project_doc_max_bytes` can truncate automatic instruction loading | DOCUMENTED | BLOCKED | Read, size and hash complete files explicitly |
| C13 | `SubagentStart` can add context but `continue: false` does not stop subagent startup | DOCUMENTED | BLOCKED | Context/audit only; qualify ephemeral-first with a controlled project-scoped non-ephemeral fallback when the recognized ephemeral parent-thread blocker occurs |
| C14 | Planning isolation preserves the source branch, SHA, index and files | CONTRACT_DEFINED | BLOCKED | Planning worktree isolation is mandatory |
| C15 | Blind review is immutable and detects seeded contract defects | CONTRACT_DEFINED | BLOCKED | Hash review before separate comparison |
| C16 | The Git probe accurately reports refs, branches, worktrees, index, commits and cleanup | CONTRACT_DEFINED | BLOCKED | No artifact generation before required Git capabilities pass |

## 4. Release gate

C01, C02, C03 and C05 through C16 must be `REPRODUCED` before production readiness. C04 is informational for PlanAnvil 2.3 because generated execution deliberately forbids nested descendants.

Baseline 2.3 does not infer C13 reproduction from transport diagnostics. Controlled Codex 0.152 runs established that `codex exec --ephemeral` can hit a parent-thread registration failure even when project roles are otherwise valid, while non-ephemeral project-agent execution can progress normally. The release-gating fallback must therefore keep both the synthetic role and the `SubagentStart` hook project-scoped and use an isolated user home only for trust, authentication bridging, and disposable persistence.

## 5. Test requirements

### Activation and discovery

Verify nested-directory discovery, explicit activation, disabled implicit activation and rejection of implementation or existing-plan execution requests.

### Agent topology

Use current documented agent configuration (`agents.enabled` and `agents.max_concurrent_threads_per_session`). Record the event tree for required reviewer/profiler dispatch. Do not rely on undocumented nesting-depth configuration. Separately assert that generated execution contracts require a flat direct-child topology.

### C13 SubagentStart qualification transport

The semantic assertion under test is the documented `SubagentStart` behavior, not `codex exec --ephemeral` persistence.

C13 therefore uses this fail-closed transport contract:

1. start with a fresh real `codex exec --ephemeral` trial using an aligned project-scoped synthetic agent (`fixture_agent.toml`, declared name `fixture_agent`) and a real project-scoped `SubagentStart` hook;
2. if that trial reaches `SubagentStart` without the recognized transport failure, evaluate the semantics directly and do not use a fallback;
3. permit a non-ephemeral retry only when the ephemeral attempt matches the recognized `collab spawn failed: no thread with id` parent-thread registration failure;
4. for that retry, create a separate disposable repository that keeps the synthetic `fixture_agent` project-scoped, explicitly declares `[agents.fixture_agent]`, and keeps the real `SubagentStart` hook project-scoped;
5. use a private disposable `CODEX_HOME` only to persist the fixture trust decision, bridge file-backed authentication, and isolate non-ephemeral session/SQLite/log state; do not move the agent or hook into the home layer;
6. keep approval `never`, C13 sandbox `read-only`, model-tool network disabled and project trust limited to the disposable fixture;
7. bridge file-backed authentication only through a temporary symlink, never read or copy the credential file, isolate SQLite/log state, disable message-history persistence, then remove the complete disposable `CODEX_HOME` and verify auth metadata is unchanged;
8. require exactly one real project-scoped `SubagentStart`, `additionalContext` from that hook, `continue=false` from the same hook, and a child echo of an opaque proof that was not present in the root-agent prompt;
9. classify missing transport/discovery evidence as `BLOCKED`, and classify contradictory behavior after the real `SubagentStart` boundary is reached as `FAILED`.

The fallback is a qualification transport exception only. It does not change PlanAnvil's project-scoped agent/hook product contract and it does not weaken sandbox, approval, trust, network or evidence-sanitization boundaries.

### File handoff

Verify explicit review/profile brief paths, expected hashes and rejection of missing, stale or escaped paths.

### Hooks and Git guards

Test direct commands, wrappers, dynamic construction, supported patch and MCP calls, non-intercepted equivalent paths and the configured unsafe Git corpus. Passing requires both preventive behavior and postcondition detection.

### Compaction and recovery

Verify manual and automatic triggers, delay without a checkpoint, allowance after a checkpoint, absence of a permanent loop, recovery-pointer injection and reconstruction from files and Git.

### Project instructions

Verify root instructions, nested overrides, fallback names, precedence, directory scope, byte limits and explicit complete-file reads.

### Git isolation

Assert source immutability, correct planning base, allowed-path-only changes, cleanup, detached-HEAD handling, signing policy and repository-hook outcomes.

### Blind review

Use seeded defects including missing rollback, uncovered requirements, risks without controls, unapproved public behavior, inconsistent base SHA and generator/executor boundary violations. The blind report and its metadata sidecar remain unchanged during comparison.

### Git capability matrix

Record separate outcomes for ordinary file writes, temporary refs, branches, linked worktrees, index updates, commits, signing, repository hooks and cleanup under every supported permission mode.

## 6. Current official documentation checked on 2026-09-02

- Skills: `https://developers.openai.com/codex/skills`
- Configuration reference: `https://developers.openai.com/codex/config-reference`
- Subagents: `https://developers.openai.com/codex/subagents`
- Hooks: `https://developers.openai.com/codex/hooks`
- AGENTS.md: `https://developers.openai.com/codex/guides/agents-md`

Baseline 2.3 keeps the semantic capability matrix from 2.2 and changes only the C13 qualification transport contract. The transport remains ephemeral-first, but a recognized Codex 0.152 parent-thread registration failure may be retried non-ephemerally without changing the project-scoped role/hook semantics under test.

The earlier 2.2 subagent decision remains: current subagent documentation exposes `agents.enabled` and `agents.max_concurrent_threads_per_session`; it does not document `agents.max_depth`. PlanAnvil therefore enforces flat topology in its generated execution contract instead of relying on a runtime depth setting.

## 7. Architecture rule

An active architecture decision may rely only on:

1. current official OpenAI documentation; or
2. a `REPRODUCED` contract test consistent with that documentation.

A disagreement blocks the affected release work until the current behavior is verified and the contract is corrected.

## 8. Evidence retention

Sanitize usernames, home directories, private repository URLs, session identifiers, credentials and proprietary source content.

Retain structural event data, sanitized command arguments, hashes, expected and actual decisions and the minimal fixture source required to evaluate the test.
