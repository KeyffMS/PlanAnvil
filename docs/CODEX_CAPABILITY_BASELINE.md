# PlanAnvil — Codex Capability Baseline

> **Baseline version:** 2.0  
> **Review date:** 2026-07-12  
> **Purpose:** define reproducible capability tests that affect PlanAnvil architecture.  
> **Important:** this file does not override current official OpenAI documentation.

## 1. Evidence classes

Each finding uses one status:

```text
DOC_CONFIRMED
REPRODUCED
OBSERVED_UNREPRODUCED
CONTRADICTED_BY_DOCS
EXPECTED_FAIL
NOT_RUN
```

`DOC_CONFIRMED` means current official documentation directly supports the behavior.

`REPRODUCED` requires committed sanitized evidence containing the complete test contract described below.

`OBSERVED_UNREPRODUCED` is historical information only. It cannot justify an active production assumption.

`CONTRADICTED_BY_DOCS` blocks use of the observation as expected current behavior.

## 2. Required evidence package

Every capability test directory MUST contain:

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

`README.md` records:

- test objective;
- verification date;
- Codex version;
- model slug;
- OS and architecture;
- permission mode;
- fixture commit;
- exact setup and cleanup;
- privacy sanitization performed.

Session transcripts, credentials, private paths, unrelated Git object databases, and user data must not be committed.

## 3. Current matrix

| ID | Current status | Capability | Active contract decision |
|---|---|---|---|
| C01 | DOC_CONFIRMED | Repository skill discovery from `.agents/skills` | Canonical skill path is `.agents/skills/plan-anvil` |
| C02 | DOC_CONFIRMED | `allow_implicit_invocation: false` disables implicit invocation | Require explicit activation |
| C03 | CONTRADICTED_BY_DOCS | Historical grandchild start with `max_depth = 1` | Do not claim this as current behavior; retain regression test |
| C04 | DOC_CONFIRMED | Nested agents can exist when depth permits | Generated contract deliberately uses flat topology |
| C05 | OBSERVED_UNREPRODUCED | Fresh subagent read an untracked file | Do not depend on this without a committed fixture |
| C06 | DOC_CONFIRMED | `PreToolUse` can deny supported Bash, `apply_patch`, and MCP calls but is incomplete | Hooks plus mandatory post-diff validation |
| C07 | OBSERVED_UNREPRODUCED | Hook blocked tested destructive Git variants | Build reproducible allowlist/denylist corpus; postconditions remain mandatory |
| C08 | DOC_CONFIRMED | `PreCompact` supports stop behavior | Delay only until a valid checkpoint exists |
| C09 | OBSERVED_UNREPRODUCED | Repeated auto-compaction blocking caused unusable behavior | Never design a permanent block loop |
| C10 | DOC_CONFIRMED | `PostCompact` and `SessionStart` support compact-related recovery context | Recovery pointer only; filesystem and Git remain authoritative |
| C11 | DOC_CONFIRMED | Nested project instructions depend on documented directory discovery | Explicitly map instructions for affected paths |
| C12 | DOC_CONFIRMED | `project_doc_max_bytes` can truncate automatic instruction loading | Explicitly read, size, and hash full files |
| C13 | DOC_CONFIRMED | `SubagentStart` `continue: false` does not block startup | Audit/context only |
| C14 | OBSERVED_UNREPRODUCED | Planning worktree isolated planning artifacts | Reproduce with source immutability assertions |
| C15 | OBSERVED_UNREPRODUCED | Blind reviewer caught a defect and immutable comparison detected false claims | Reproduce with golden defective plans |
| C16 | OBSERVED_UNREPRODUCED | Workspace writes succeeded while `.git` metadata writes failed | Run full Git capability probe in supported permission modes |

## 4. Critical tests required before release

The following tests must reach `REPRODUCED` before production readiness:

```text
C01 skill discovery
C02 explicit activation
C06 supported hook denial plus bypass detection
C07 destructive Git corpus
C11 instruction scope and precedence
C12 instruction truncation
C13 SubagentStart non-blocking behavior
C14 planning worktree isolation
C15 immutable blind review
C16 Git metadata permission matrix
```

C03 must be rerun as a regression test. Expected current behavior follows official documentation: a child may not spawn a grandchild when `agents.max_depth = 1`.

## 5. Test design

### C01 — Skill discovery

Verify discovery from:

- repository root `.agents/skills`;
- nested current working directory with root skill;
- duplicate skill-name behavior;
- explicit invocation.

### C02 — Activation policy

Verify:

- ordinary code request does not activate PlanAnvil;
- `$plan-anvil` activates it;
- immediate implementation request does not make the skill execute a plan;
- executing an existing plan is rejected as out of scope.

### C03/C04 — Depth and nesting

Run with depth values:

```text
0
1
2
```

Record the complete agent event tree and expected spawn results.

No security gate may depend solely on this test.

### C06/C07 — Hooks

Test at least:

- direct Bash command;
- shell wrapper;
- dynamic command construction;
- `apply_patch`;
- supported MCP write;
- an equivalent path not intercepted by the hook;
- stash, reset, clean, checkout-overwrite, and ref deletion variants.

A successful test demonstrates both hook behavior and postcondition detection.

### C08/C09/C10 — Compaction

Verify:

- manual and automatic triggers;
- missing-checkpoint delay;
- valid-checkpoint allowance;
- no repeated permanent stop loop;
- compact recovery pointer;
- reconciliation from files and Git.

### C11/C12 — Instructions

Verify:

- root instructions;
- nested override;
- configured fallback;
- precedence;
- exact directory scope;
- 32 KiB default-limit behavior when applicable;
- configured larger limit;
- explicit full-file read.

### C14 — Git isolation

Assert:

- source branch and SHA unchanged;
- source index and files unchanged;
- planning branch based on expected SHA;
- only approved planning paths changed;
- cleanup of probe refs and worktrees;
- detached-HEAD behavior;
- signing and repository-hook outcomes.

### C15 — Blind review

Use golden plans with seeded defects:

- missing rollback;
- uncovered requirement;
- risk without a control;
- public behavior without approval;
- inconsistent base SHA;
- unauthorized generator execution instruction.

Hash the blind report before comparison and assert it remains unchanged.

### C16 — Permission matrix

Run the complete Git probe under every supported Codex permission mode available in the tested client.

Record results separately for:

- ordinary file write;
- temporary ref;
- branch;
- linked worktree;
- index;
- commit;
- cleanup.

## 6. Architecture rule

An active architecture decision may rely on:

1. current official documentation; or
2. a `REPRODUCED` test that is not contradicted by official documentation.

Historical prose alone is insufficient.

## 7. Evidence retention policy

Sanitize:

- usernames;
- home directories;
- repository URLs when private;
- session IDs;
- tokens and credentials;
- proprietary source content.

Retain:

- structural event data;
- command arguments after secret removal;
- hashes;
- expected and actual decisions;
- minimal fixture source created for the test.

A sanitizer must not remove the evidence required to evaluate the capability.
