# PlanAnvil — Implementation Specification

> **Contract version:** 2.1  
> **Status:** authoritative implementation contract  
> **Target:** native OpenAI Codex repository skill  
> **Core boundary:** PlanAnvil generates and validates an implementation plan. It never executes that plan.

## 1. Product goal

PlanAnvil converts a software-engineering goal into a rigorous, test-driven and auditable implementation contract for a separate later Codex run.

A generated plan must support:

- strict Git and worktree isolation;
- explicit project-instruction discovery;
- repository and environment profiling;
- atomic, independently verifiable stages;
- acceptance criteria defined before implementation;
- risk-driven tests and controls;
- blind independent review;
- durable file-based state;
- explicit integration, production-verification and rollback procedures;
- minimal dependence on conversational memory.

PlanAnvil is not a coding agent, executor, task manager or wrapper around another development framework.

## 2. Authority

The words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT** and **MAY** are normative.

When documents disagree, use this order:

1. current official OpenAI Codex documentation;
2. this specification;
3. `docs/ARCHITECTURE.md`;
4. `docs/ARTIFACT_SCHEMAS.md`;
5. `docs/OPENAI_COMPLIANCE.md`;
6. `docs/CODEX_CAPABILITY_BASELINE.md`;
7. examples and README.

A capability test may strengthen a documented limitation. It must not override current official documentation unless the discrepancy is reproducible, version-scoped and recorded in `OPENAI_COMPLIANCE.md`.

## 3. Generator and executor are separate

### 3.1 PlanAnvil runtime

PlanAnvil MUST:

1. inspect the source repository without changing it;
2. verify Git state and every Git capability it will use;
3. create an isolated planning branch and planning worktree;
4. create or validate profiles inside the planning worktree;
5. discover all applicable project instructions;
6. analyze the goal and repository evidence;
7. generate `PLAN.md`, stage briefs and machine-readable artifacts;
8. run deterministic validation;
9. run a fresh blind plan review and a separate comparison;
10. commit only approved planning artifacts;
11. report the branch, commit, plan path, assumptions, unknowns and status;
12. stop.

PlanAnvil MUST NOT:

- modify application code or application tests;
- execute a generated implementation stage;
- create a task implementation branch;
- run migrations, deploy or restart services;
- switch a live system;
- create an implementation integration merge;
- merge or push to the base branch;
- use `git stash`, `git reset` or `git clean` to hide or discard work;
- start the future execution orchestrator;
- continue into execution after approval in the same run.

### 3.2 Generated execution contract

Jim, Jenny, implementation agents, task and integration branches, retry strategies, implementation test cycles and live verification exist only as requirements written into the generated plan.

PlanAnvil may use separate read-only planning agents. They are not the future execution roles.

A validator MUST reject any plan or implementation that conflates the generator run with the later execution run.

## 4. Implementation platform and installation

The first production implementation MUST use:

- Python 3.11 or newer;
- Python standard library only for core deterministic scripts;
- Git 2.30 or newer;
- UTF-8 and LF line endings for canonical files;
- JSON for canonical machine state;
- Markdown for human-readable contracts and reports.

Supported systems are Linux, macOS and Windows with Python and Git installed.

The implementation MUST NOT require elevated privileges, `sudo`, network access for local validation, installation of project dependencies merely to generate a plan, or undocumented Codex mechanisms.

The canonical skill path is:

```text
.agents/skills/plan-anvil/
```

Skill metadata MUST contain:

```yaml
policy:
  allow_implicit_invocation: false
```

PlanAnvil activates only after an explicit request such as `$plan-anvil`.

The v1 core is a repository skill. Project-scoped `.codex/` agents and hooks are optional defense-in-depth integration. Plugin packaging is outside v1.

## 5. Generator lifecycle

The mandatory order is:

```text
SOURCE_PREFLIGHT
→ GIT_CAPABILITY_CHECK
→ CREATE_PLANNING_BRANCH_AND_WORKTREE
→ CREATE_OR_VALIDATE_PROFILES
→ DISCOVER_INSTRUCTIONS
→ ANALYZE_GOAL
→ GENERATE_ARTIFACTS
→ DETERMINISTIC_VALIDATION
→ BLIND_PLAN_REVIEW
→ COMPARISON_AND_FINAL_VALIDATION
→ COMMIT_PLANNING_ARTIFACTS
→ REPORT_AND_STOP
```

No state may be skipped.

No profile or run artifact is written before the planning worktree exists. The source worktree remains on its original branch and commit and its files and index remain unchanged.

When a user supplies a planning branch and linked worktree because Codex cannot write Git metadata, PlanAnvil validates them and starts at profile creation.

## 6. Source preflight

Preflight MUST be read-only and verify:

- Git exists;
- the current directory is inside a Git repository;
- repository root and `HEAD` are resolvable;
- no modified, staged or untracked files exist;
- no conflicts exist;
- no merge, rebase, cherry-pick, revert, bisect or equivalent unsafe operation is active;
- linked worktrees can be listed.

Preflight must not create files, refs, branches, commits or repository-local temporary directories.

## 7. Git capability contract

The Git check returns one primary result:

```text
GIT_READY
GIT_UNAVAILABLE
NOT_A_GIT_REPOSITORY
GIT_DIRTY
GIT_OPERATION_IN_PROGRESS
GIT_READ_ONLY
GIT_WRITE_RESTRICTED
GIT_IDENTITY_MISSING
GIT_SIGNING_BLOCKED
GIT_HOOK_BLOCKED
GIT_WORKTREE_UNSUPPORTED
GIT_BASE_AMBIGUOUS
```

Plan status mapping is deterministic:

| Git result | Plan status |
|---|---|
| `GIT_READY` | continue |
| `GIT_DIRTY`, `GIT_OPERATION_IN_PROGRESS`, `GIT_BASE_AMBIGUOUS` | `BLOCKED_BY_GIT_STATE` |
| `GIT_READ_ONLY`, `GIT_WRITE_RESTRICTED` | `BLOCKED_BY_GIT_PERMISSIONS` |
| all other non-ready results | `BLOCKED_BY_RUNTIME_PREREQUISITE` |

### 7.1 Base resolution

When `HEAD` is attached, the current branch is the base candidate.

For detached `HEAD`, PlanAnvil must establish one unambiguous appropriate containing branch. Otherwise it stops with `GIT_BASE_AMBIGUOUS`. It must not choose from branch names alone.

### 7.2 Reversible capability probe

Before creating planning artifacts, PlanAnvil MUST test:

1. temporary ref creation, verification and deletion;
2. probe branch creation from `BASE_SHA`;
3. linked probe-worktree creation;
4. probe-file creation and removal;
5. index update;
6. a real probe commit using the current identity, signing and repository-hook policy;
7. worktree removal and branch deletion;
8. confirmation that the source branch, `HEAD`, index and files are unchanged.

Use unique names such as:

```text
refs/plananvil/probes/<RUN-ID>
plananvil/probe/<RUN-ID>
```

The commit step may not be skipped while returning `GIT_READY`. A signing or hook failure returns `GIT_SIGNING_BLOCKED` or `GIT_HOOK_BLOCKED`.

A ref-only probe is insufficient.

PlanAnvil never elevates privileges or bypasses the sandbox. For restricted Git metadata writes it may only explain the required permission mode or ask the user to create the planning branch and worktree manually.

## 8. Worktree and artifact ownership

### 8.1 Source worktree

The source worktree is read-only for PlanAnvil.

### 8.2 Planning worktree

For `GIT_READY`, create:

```text
Planning branch: pursue/plan/<PLAN-ID>/<slug>
Planning worktree: an external path selected deterministically by the implementation
```

The planning branch may contain only:

- `.pursue/SYSTEM_PROFILE.md`;
- ignore rules for local PlanAnvil files;
- generated plan and control artifacts;
- later execution-control and evidence artifacts for this plan;
- documentation directly required by the plan.

It must never contain product implementation or product tests.

The planning worktree is the durable **control root**. The later executor reads the immutable plan there, writes state, checkpoints, reports and evidence there, and performs product changes only in task or integration worktrees.

During execution, `PLAN.md`, stage briefs and approved acceptance criteria are immutable unless the generated plan-change protocol creates a versioned replacement and renews validation.

Execution-control artifacts may be committed to the planning branch at verified checkpoints. Product-code commits belong only to the task branch.

### 8.3 Local paths and privacy

Committed artifacts MUST NOT contain absolute local filesystem paths, usernames or machine-specific service locations.

Each run has an ignored local file:

```text
.pursue/runs/<RUN-ID>/local-state.json
```

It stores absolute source, planning and local-profile paths plus required local hashes. It is never committed or pushed.

`manifest.json` stores only repository identity, branch and commit identity, and repository-relative paths. The final terminal report may display absolute paths transiently.

The planning worktree remains available until execution finishes, the plan is rejected or it is explicitly archived.

PlanAnvil does not push the planning branch unless separately requested and the profile confirms that the push is safe.

## 9. Profiles

Profiles are created after planning isolation and before goal analysis.

### 9.1 Repository profile

`.pursue/SYSTEM_PROFILE.md` is versioned and contains repository-safe facts including:

- repository structure and architecture;
- languages, runtimes and dependency managers;
- build, test, lint and static-analysis commands;
- Git conventions and quality gates;
- instruction map;
- general deployment, state and rollback rules;
- activation recommendation policy and risk thresholds;
- evidence and freshness metadata.

### 9.2 Local profile

`.pursue/SYSTEM_PROFILE.local.md` is ignored and contains machine-specific but non-secret information including local paths, service names, process-manager commands, health checks, switch and rollback procedures, permission requirements and push-trigger implications.

It must not contain passwords, tokens, credentials, private keys, certificates, cookies or copied `.env` content.

### 9.3 Evidence and freshness

Facts use `VERIFIED`, `USER_CONFIRMED`, `INFERRED` or `UNKNOWN`.

Profile validity uses `VALID`, `VALID_WITH_UNKNOWNS`, `PARTIALLY_STALE`, `STALE` or `UNVERIFIABLE`.

Verified facts identify their evidence. Freshness is based primarily on hashes of instruction, dependency, test, build, deployment, migration and PlanAnvil configuration files.

## 10. Project instructions

PlanAnvil MUST discover all applicable:

- `AGENTS.override.md`;
- `AGENTS.md`;
- configured fallback instruction filenames supported by Codex;
- nested instruction files within affected paths.

For each file record path, hash, byte size, full-read status, directory scope, precedence, affected stages, conflicts, truncation risk and safety-critical rules.

Automatically loaded content is not assumed complete. Full files must be read explicitly.

Documented scope and precedence resolve conflicts first. Remaining non-critical ambiguity uses the best-supported interpretation preserving project intent, safety, expected outcome, architecture and minimal change.

An inferred interpretation never overrides an explicit prohibition involving security, secrets, protected data, destructive operations, production, irreversible changes, branch protection, law or compliance.

A remaining safety-critical conflict produces `BLOCKED_BY_INSTRUCTION_CONFLICT`.

## 11. Run artifacts and schemas

Each run creates:

```text
.pursue/runs/<TIMESTAMP>_<PLAN-ID>_<SLUG>/
├── PLAN.md
├── manifest.json
├── state.json
├── compliance.json
├── local-state.json        # ignored, never committed
├── stages/
├── checkpoints/
├── reports/
├── risks/
├── evidence/
├── diffs/
├── logs/
├── incidents/
└── final/
```

Timestamp format is `YYYYMMDDTHHMMSSZ`.

Canonical committed state is JSON. Markdown may mirror state but never overrides it.

All JSON artifacts conform to versioned schemas from `docs/ARTIFACT_SCHEMAS.md` and `.agents/skills/plan-anvil/schemas/`.

Mutable canonical files use write-to-temporary-file, flush, fsync where supported, atomic replace and reread validation.

## 12. Plan contract

`PLAN.md` contains stable decisions and guardrails. Stage-specific execution details belong in `stages/*.md`.

It must include:

- identity and contract version;
- a separate execution-run prompt;
- outcome and definition of done;
- generator stop boundary and executor stop conditions;
- scope and exclusions;
- assumptions, unknowns and evidence;
- applicable instructions and conflict resolutions;
- system, component, data and state-flow summaries;
- dependencies and change classification;
- stable stage index and acceptance criteria;
- requirement-stage-risk-control-evidence traceability;
- testing, Git, integration, production verification and rollback procedures;
- context, agent, resume and reconciliation rules;
- status model, next action and final-report requirements.

The plan must describe primarily what must be true. It must not contain speculative full implementations, unsupported signatures, stale permanent line numbers, unverified deployment commands, `TBD` or `TODO` placeholders.

## 13. Atomic stages and traceability

Each stage has:

- a permanent stable identifier;
- one-sentence outcome;
- scope and exclusions;
- affected paths or a discovery procedure;
- applicable instructions;
- dependencies and conflicts;
- acceptance criteria;
- risks and controls;
- one modifier role at a time;
- independent verification;
- one coherent implementation commit;
- one verified control checkpoint.

Split a stage when it spans independent domains, unrelated responsibilities, separate criteria, distinct risks or independently deployable or rollbackable work.

Traceability follows:

```text
Requirement
→ Stage
→ Acceptance criterion
→ Risk
→ Test or control
→ Evidence artifact
→ Verification result
```

A critical gap blocks `PLAN_READY`.

## 14. Ambiguity and user decisions

For non-critical ambiguity, PlanAnvil makes the best supported interpretation, records evidence and confidence and states how it will be verified.

Use `BLOCKED_BY_CRITICAL_UNKNOWN` when missing information prevents safe definition of expected behavior, critical acceptance evidence, migration behavior, rollback, public API behavior, production switching, irreversible action or security and permission behavior.

Ask the user only when a decision cannot be safely derived and changes:

- business outcome or feature scope;
- public behavior or API;
- architecture between viable choices with materially different consequences;
- data-loss or irreversible behavior;
- security, privacy, legal or permission policy;
- live-system switching;
- base-branch push or merge;
- a critical unknown blocking criteria or rollback.

Naming, internal file layout, script structure, validation order and non-critical ambiguity are implementation decisions.

## 15. Validation and blind review

Before `PLAN_READY`, deterministic validators check:

- required files and schema versions;
- no product-code or product-test changes in the control root;
- source-worktree immutability;
- planning-branch path allowlist;
- local files are ignored and absent from the commit;
- instruction completeness;
- stable identifiers and traceability;
- risk-control coverage;
- absence of placeholders;
- consistency between JSON state and Markdown contracts.

A fresh reviewer receives the goal, plan, stage briefs, profiles, instruction map, traceability, risks and validator output, but not planner reasoning or self-review.

The blind conclusion and metadata are hashed before comparison and remain immutable.

Readiness requires deterministic validation and blind-review comparison to pass.

## 16. Optional Codex integration

Project hooks and custom planning agents are optional defense in depth.

When shipped or installed, they live under:

```text
.codex/config.toml
.codex/hooks.json
.codex/hooks/
.codex/agents/
```

The implementation documents trust and enablement and works correctly when project hooks are disabled, untrusted or unavailable.

For JSON hook definitions, Windows override uses `commandWindows`. TOML may use `command_windows` or `commandWindows` as supported by current official documentation.

`SubagentStart` is context and audit only, never a startup blocker.

Every protected boundary also requires explicit role instructions, least-privilege sandboxing where available, deterministic path checks, post-agent filesystem and Git verification and checkpoint rejection on violations.

## 17. Generated execution contract

The generated plan defines a flat direct-child topology:

```text
Jim
├── analysis agent
├── Jenny
├── implementation agent
├── independent verifier
└── Winston Wolfe, after exhausted strategies only
```

Jim manages sequencing, agents, control files, checkpoints and gates but never modifies product code or tests.

Jenny modifies only approved test paths and test infrastructure and never production code.

Only one agent may modify repository files at a time.

Behavior-changing stages use:

```text
GREEN BASELINE
→ EXPECTED RED
→ IMPLEMENTATION
→ FULL GREEN
→ INDEPENDENT VERIFICATION
```

The red result must fail for the intended behavioral reason. Non-behavior stages use an equivalent evidence cycle.

Retry model:

```text
STRATEGY-A: ATTEMPT-A1, ATTEMPT-A2, ATTEMPT-A3
STRATEGY-B: ATTEMPT-B1, ATTEMPT-B2, ATTEMPT-B3
```

After three implementation failures, a materially different strategy is required. After six failures, Winston Wolfe performs read-only incident analysis and execution stops with `BLOCKED_BY_UNRESOLVED_FAILURE`.

Infrastructure failures consume an attempt only when caused by the implementation. Failed attempts remain auditable.

The later executor creates:

```text
Task branch: pursue/<PLAN-ID>/<slug>
Integration branch: pursue/integration/<PLAN-ID>/<slug>
```

Each completed stage ends in one coherent implementation-and-test commit.

The executor never pushes or merges to the base branch automatically.

Explicit user approval is required before changing the active local environment, switching a live worktree or service, executing an irreversible operation, or merging or pushing to the base branch.

Stateful stages use discover, recovery point, expand, migrate, switch, observe and separate later contraction. Irreversible actions require separate explicit approval.

## 18. Resume and compaction

Generation and execution are resumable from files and Git without previous conversation memory.

A checkpoint records stage, phase, result, branch, worktree identity, SHA, test evidence, Git status, risks, agent-tree audit, write-scope audit, next action, recovery instructions and artifact hashes.

Before compaction, a valid checkpoint must exist. `PreCompact` may delay compaction only until that checkpoint is durable.

After compaction:

```text
POST_COMPACT_EVENT
→ RECOVERY_POINTER
→ READ_MANIFEST_STATE_LOCAL_STATE_CHECKPOINT_PROFILES
→ RECONCILE_WITH_GIT
→ CONTINUE_OR_STOP
```

Conversation and hook context are never the source of truth.

## 19. Status model

Plan generation:

```text
PLAN_READY
BLOCKED_BY_CRITICAL_UNKNOWN
BLOCKED_BY_GIT_STATE
BLOCKED_BY_GIT_PERMISSIONS
BLOCKED_BY_INSTRUCTION_CONFLICT
BLOCKED_BY_RUNTIME_PREREQUISITE
PLAN_VALIDATION_FAILED
```

Generated execution:

```text
EXECUTION_READY
EXECUTION_IN_PROGRESS
READY_FOR_LOCAL_INTEGRATION_TEST
AWAITING_USER_VALIDATION
USER_ACCEPTED
USER_REJECTED
BLOCKED_BY_UNRESOLVED_FAILURE
```

`USER_ACCEPTED` does not authorize base-branch integration.

## 20. Unsupported mechanisms

Undocumented or unavailable Codex mechanisms must not be simulated or claimed.

When a requirement cannot be implemented:

1. stop affected work;
2. verify current official documentation;
3. reproduce behavior safely when possible;
4. record the conflict and evidence;
5. preserve intent with a documented mechanism;
6. remove unsupported active behavior when no safe mechanism exists.

There is no `PARTIALLY_SUPPORTED` production behavior. A mechanism is active and validated, optional defense in depth, or absent.

## 21. Target repository layout

```text
PlanAnvil/
├── README.md
├── LICENSE
├── CHANGELOG.md
├── AGENTS.md
├── docs/
│   ├── IMPLEMENTATION_SPEC.md
│   ├── ARCHITECTURE.md
│   ├── ARTIFACT_SCHEMAS.md
│   ├── OPENAI_COMPLIANCE.md
│   ├── CODEX_CAPABILITY_BASELINE.md
│   └── EXAMPLES.md
├── .agents/skills/plan-anvil/
│   ├── SKILL.md
│   ├── agents/openai.yaml
│   ├── references/
│   ├── templates/
│   ├── schemas/
│   ├── scripts/
│   └── tests/
├── .codex/                    # optional defense-in-depth integration
│   ├── config.toml
│   ├── agents/
│   ├── hooks.json
│   └── hooks/
└── examples/
    ├── small-change/
    ├── stateful-change/
    ├── blocked-plan/
    └── git-write-restricted/
```

`SKILL.md` stays narrow. Detailed rules live in references, schemas, templates and deterministic scripts.

## 22. Required tests

The implementation MUST have reproducible tests for:

- explicit activation and disabled implicit invocation;
- clean and dirty preflight states;
- every Git result and its plan-status mapping;
- mandatory probe-commit behavior;
- detached-HEAD base resolution;
- source-worktree immutability;
- planning and task worktree isolation;
- committed-manifest privacy and ignored local state;
- profile creation, freshness and secret rejection;
- instruction discovery, precedence, fallback names and truncation;
- small, large, stateful, irreversible and blocked plans;
- stable identifiers and traceability;
- JSON schemas and atomic updates;
- blind immutable review;
- hook-enabled, disabled, untrusted and unavailable modes;
- execution-control artifact ownership;
- recovery and compaction contracts;
- Linux, macOS and Windows behavior;
- observable stop after validation.

Capability tests retain exact commands or prompts, Codex version, model slug, OS, configuration, fixture commit, expected result, sanitized actual result and evaluation.

## 23. Completion criteria

PlanAnvil is complete only when:

1. native discovery and explicit activation work;
2. the generator and executor boundary is enforced;
3. lifecycle order is enforced;
4. source preflight is read-only;
5. the complete Git probe succeeds or reports a precise blocker;
6. source, planning and task worktrees have correct ownership;
7. profiles are created in the planning worktree;
8. local profile and local state are ignored and secret-safe;
9. committed artifacts contain no local absolute paths;
10. instructions are mapped and fully read;
11. canonical state passes versioned schemas;
12. every run has a unique durable control directory;
13. plans and stages use stable identifiers;
14. traceability has no critical gaps;
15. critical unknowns block readiness;
16. blind review remains immutable;
17. hooks remain optional defense in depth;
18. postconditions remain mandatory without hooks;
19. generated plans define testing, Git, integration, live verification, rollback, recovery and approvals;
20. capability tests are reproducible;
21. `OPENAI_COMPLIANCE.md` has no active contradiction;
22. README accurately describes status and use.

## 24. Implementation workflow

The implementing agent MUST:

1. read repository instructions and normative documents;
2. verify a clean worktree and create a dedicated implementation branch;
3. re-check current official OpenAI documentation;
4. implement architecture and schemas before prompts;
5. implement the native skill skeleton;
6. implement read-only preflight and the complete Git probe;
7. implement planning-worktree creation;
8. implement profiles and instruction mapping;
9. implement schemas, local-state privacy and atomic writes;
10. implement deterministic validation;
11. implement blind review and comparison;
12. add optional hooks and planning-agent profiles;
13. implement reproducible capability fixtures;
14. run available cross-platform gates;
15. review golden examples;
16. verify no secrets or machine-specific paths are committed;
17. verify the generator cannot modify product code or tests;
18. commit coherent units;
19. push only when explicitly authorized;
20. report exact evidence and blockers.

## 25. Non-goals

PlanAnvil does not execute generated plans, implement product code or tests, automatically merge or push a base branch, elevate permissions, manage secrets, create staging infrastructure, guarantee reversal of irreversible actions, ignore explicit safety instructions, allow parallel repository modification, rely solely on hooks or conversational memory, integrate with Superpowers, or make the final business-acceptance decision.
