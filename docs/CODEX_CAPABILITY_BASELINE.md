# PlanAnvil — Codex Capability Baseline

> **Baseline version:** 2.2  
> **Review date:** 2026-08-28  
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
| C13 | `SubagentStart` can add context but `continue: false` does not stop subagent startup | DOCUMENTED | BLOCKED | Context and audit only |
| C14 | Planning isolation preserves the source branch, SHA, index and files | CONTRACT_DEFINED | BLOCKED | Planning worktree isolation is mandatory |
| C15 | Blind review is immutable and detects seeded contract defects | CONTRACT_DEFINED | BLOCKED | Hash review before separate comparison |
| C16 | The Git probe accurately reports refs, branches, worktrees, index, commits and cleanup | CONTRACT_DEFINED | BLOCKED | No artifact generation before required Git capabilities pass |

## 4. Release gate

C01, C02, C03 and C05 through C16 must be `REPRODUCED` before production readiness. C04 is informational for PlanAnvil 2.2 because generated execution deliberately forbids nested descendants.

The 2026-08-28 qualification attempt is `BLOCKED` for live Codex reproduction because the available execution environment does not expose an authenticated Codex runtime or `codex` executable. Deterministic contract tests remain useful supporting evidence but cannot substitute for the required live packages.

## 5. Test requirements

### Activation and discovery

Verify nested-directory discovery, explicit activation, disabled implicit activation and rejection of implementation or existing-plan execution requests.

### Agent topology

Use current documented agent configuration (`agents.enabled` and `agents.max_concurrent_threads_per_session`). Record the event tree for required reviewer/profiler dispatch. Do not rely on undocumented nesting-depth configuration. Separately assert that generated execution contracts require a flat direct-child topology.

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

## 6. Current official documentation checked on 2026-08-28

- Skills: `https://developers.openai.com/codex/skills`
- Configuration reference: `https://developers.openai.com/codex/config-reference`
- Subagents: `https://developers.openai.com/codex/subagents`
- Hooks: `https://developers.openai.com/codex/hooks`
- AGENTS.md: `https://developers.openai.com/codex/guides/agents-md`

Notable drift from baseline 2.1: current subagent documentation exposes `agents.enabled` and `agents.max_concurrent_threads_per_session`; it does not document `agents.max_depth`. `agents.max_threads` is retained only as a legacy concurrency alias. PlanAnvil therefore enforces flat topology in its generated execution contract instead of relying on a runtime depth setting.

## 7. Architecture rule

An active architecture decision may rely only on:

1. current official OpenAI documentation; or
2. a `REPRODUCED` contract test consistent with that documentation.

A disagreement blocks the affected release work until the current behavior is verified and the contract is corrected.

## 8. Evidence retention

Sanitize usernames, home directories, private repository URLs, session identifiers, credentials and proprietary source content.

Retain structural event data, sanitized command arguments, hashes, expected and actual decisions and the minimal fixture source required to evaluate the test.
