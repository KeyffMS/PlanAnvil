# PlanAnvil — Codex Capability Baseline

> **Baseline version:** 2.1  
> **Review date:** 2026-07-12  
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

`REPRODUCED` requires a committed, sanitized evidence package. Informal observations and remembered runtime behavior are not valid architecture inputs.

## 2. Required evidence package

Each test directory contains:

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
| C01 | Repository skills are discovered from `.agents/skills` | DOCUMENTED | NOT_RUN | Use `.agents/skills/plan-anvil` |
| C02 | `allow_implicit_invocation: false` disables implicit invocation | DOCUMENTED | NOT_RUN | Require explicit `$plan-anvil` activation |
| C03 | `agents.max_depth = 1` permits direct children and prevents deeper descendants | DOCUMENTED | NOT_RUN | Use depth `1` for the flat topology and audit actual evidence as an additional control |
| C04 | Nested agents are available when configured depth permits them | DOCUMENTED | NOT_RUN | Generated execution remains deliberately flat |
| C05 | Planning-agent handoffs use explicit files and hashes | CONTRACT_DEFINED | NOT_RUN | Reject missing, stale or out-of-root briefs |
| C06 | `PreToolUse` covers supported calls but not every equivalent path | DOCUMENTED | NOT_RUN | Hooks plus mandatory postcondition validation |
| C07 | The Git guard rejects the configured unsafe-command corpus | CONTRACT_DEFINED | NOT_RUN | Git postconditions remain mandatory |
| C08 | `PreCompact` can stop compaction | DOCUMENTED | NOT_RUN | Delay only until a valid checkpoint exists |
| C09 | Compaction is allowed after checkpoint creation without a permanent stop loop | CONTRACT_DEFINED | NOT_RUN | Checkpoint, allow, recover and reconcile |
| C10 | `PostCompact` and `SessionStart` can provide recovery context | DOCUMENTED | NOT_RUN | Inject only a recovery pointer |
| C11 | Project instructions follow documented directory scope and precedence | DOCUMENTED | NOT_RUN | Explicitly map affected instructions |
| C12 | `project_doc_max_bytes` may truncate automatic instruction loading | DOCUMENTED | NOT_RUN | Read, size and hash complete files explicitly |
| C13 | `SubagentStart` can add context but is not a startup blocker | DOCUMENTED | NOT_RUN | Context and audit only |
| C14 | Planning isolation preserves the source branch, SHA, index and files | CONTRACT_DEFINED | NOT_RUN | Planning worktree isolation is mandatory |
| C15 | Blind review is immutable and detects seeded contract defects | CONTRACT_DEFINED | NOT_RUN | Hash review before separate comparison |
| C16 | The Git probe accurately reports refs, branches, worktrees, index, commits and cleanup | CONTRACT_DEFINED | NOT_RUN | No artifact generation before required Git capabilities pass |

## 4. Release gate

C01, C02, C03 and C06 through C16 must be `REPRODUCED` before production readiness. C04 and C05 are required when the corresponding agent features are enabled.

## 5. Test requirements

### Activation and discovery

Verify nested-directory discovery, explicit activation, disabled implicit activation and rejection of implementation or existing-plan execution requests.

### Agent topology

Run with depth values `0`, `1` and `2`. Record the complete event tree and assert the behavior defined by current official documentation. Agent evidence is audited before a quality gate is accepted.

### File handoff

Verify explicit brief paths, expected hashes and rejection of missing, stale or escaped paths.

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

## 6. Architecture rule

An active architecture decision may rely only on:

1. current official OpenAI documentation; or
2. a `REPRODUCED` contract test consistent with that documentation.

A disagreement blocks the affected release work until the current behavior is verified and the contract is corrected.

## 7. Evidence retention

Sanitize usernames, home directories, private repository URLs, session identifiers, credentials and proprietary source content.

Retain structural event data, sanitized command arguments, hashes, expected and actual decisions and the minimal fixture source required to evaluate the test.
