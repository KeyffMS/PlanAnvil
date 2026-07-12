# PlanAnvil — Implementation Specification

> **Repository:** https://github.com/KeyffMS/PlanAnvil
> **Document purpose:** define the complete product contract for the first production-ready implementation.
> **Target runtime:** native OpenAI Codex, optimized for GPT-5.6 Sol.
> **Important:** this document defines what must be built. It is not the final `SKILL.md`.

## 1. Product goal

Build **PlanAnvil**, a Codex-native skill whose only responsibility is to generate a rigorous, test-driven, auditable implementation contract for a software-engineering goal.

PlanAnvil must **create and validate a plan but never execute it**.

A generated plan must be suitable for a separate later Codex run that can perform long-running repository work with:

- strict Git isolation;
- mandatory project-instruction discovery;
- repository and environment profiling;
- atomic, independently verifiable stages;
- acceptance criteria defined before tests;
- risk-driven testing;
- independent blind verification;
- resumable file-based state;
- explicit production and rollback procedures;
- minimal memory usage in the main orchestrator context.

PlanAnvil is not a general coding agent, task manager, autonomous executor, or wrapper around another development framework.

## 2. Codex compatibility problems and required solutions

PlanAnvil must be designed around current documented Codex behavior and the verified capability baseline in `docs/CODEX_CAPABILITY_BASELINE.md`.

### 2.1 Native skill location

Repository skills must use the native Codex location:

```text
.agents/skills/plan-anvil/
```

Do not use a repository-root `skills/` directory as the active Codex installation path.

The final skill must use:

```yaml
policy:
  allow_implicit_invocation: false
```

PlanAnvil may still provide installation tooling, but its canonical checked-in form must remain Codex-native.

### 2.2 Agent depth is a capability, not a security boundary

Codex supports nested subagents. Capability tests also showed that a grandchild could start even in a test configured with `agents.max_depth = 1`.

Therefore:

- PlanAnvil may acknowledge that nested agents are technically possible;
- the generated execution contract must still use a flat topology;
- all technical agents must be direct children of Jim;
- no security or correctness guarantee may depend only on `agents.max_depth`;
- an unexpected descendant is a contract violation;
- results from an unauthorized descendant must not satisfy a quality gate.

PlanAnvil may recommend `agents.max_depth = 1` as defense in depth, but it must independently audit the actual agent tree.

### 2.3 `SubagentStart` is audit-only

`SubagentStart` may be used to:

- log the agent identifier and type;
- inject mandatory project instructions;
- record parent-child relationships;
- detect an unauthorized agent;
- add a model-visible warning.

It must not be treated as a guaranteed start blocker. A capability test confirmed that returning `continue: false` did not prevent the subagent from starting.

### 2.4 Hooks are defense in depth, not the sole enforcement boundary

`PreToolUse` hooks may block known Bash commands, `apply_patch` writes, and supported MCP tool calls. Tests confirmed effective blocking of forbidden paths and destructive Git commands in the tested runtime.

However, PlanAnvil must follow the official limitation that hooks do not intercept every equivalent tool path.

Therefore every write boundary requires all of:

1. least-privilege sandbox configuration;
2. explicit agent instructions;
3. `PreToolUse` allowlists or denylists where supported;
4. post-agent filesystem and Git diff verification;
5. checkpoint rejection when unauthorized changes are found.

Hooks must never be the only control protecting production code, tests, Git history, or stateful resources.

### 2.5 Nested `AGENTS.md` files are not loaded merely because a path is discussed

Capability testing confirmed that a nested instruction file becomes active based on the session working directory and documented instruction discovery, not merely because an agent plans to touch a nested path.

Therefore PlanAnvil must explicitly:

- discover every applicable instruction file;
- calculate its directory scope;
- calculate precedence;
- detect truncation risk;
- include the exact applicable instruction paths in every stage brief;
- require every fresh agent to read the full applicable files before work.

### 2.6 Instruction files may be truncated

Codex limits the combined automatically loaded instruction size through `project_doc_max_bytes`. Capability testing confirmed real truncation behavior.

The profiler must:

- record the configured limit when discoverable;
- record the byte size and hash of every instruction file;
- detect when automatic loading could be incomplete;
- explicitly read full instruction files during profiling;
- mark the instruction map invalid if a critical file cannot be read in full.

### 2.7 Git metadata writes may require higher permissions

Creating refs, branches, commits, and worktrees requires writes under `.git`. Capability testing confirmed that a standard `workspace-write` sandbox may permit normal file edits while blocking Git metadata writes.

PlanAnvil must run a Git capability test before creating planning artifacts and report one of:

```text
GIT_READY
GIT_READ_ONLY
GIT_WRITE_RESTRICTED
GIT_DIRTY
GIT_OPERATION_IN_PROGRESS
NOT_A_GIT_REPOSITORY
```

When the result is `GIT_READ_ONLY` or `GIT_WRITE_RESTRICTED`, PlanAnvil must stop and explain that one of the following is required:

- a Codex permission mode that permits Git metadata writes; or
- a planning branch and worktree created manually by the user.

PlanAnvil must never attempt to grant itself higher privileges, invoke `sudo`, or bypass the sandbox.

### 2.8 Compaction must use checkpoint, compact, and recovery

`PreCompact` can stop both manual and automatic compaction. Tests confirmed this behavior, but also showed that permanently blocking automatic compaction after crossing the threshold can make a session practically unusable.

The required policy is:

```text
CHECKPOINT
→ ALLOW COMPACTION
→ POST-COMPACT EVENT
→ SESSION RECOVERY CONTEXT
→ RECONCILIATION
→ CONTINUE
```

`PreCompact` may delay compaction only long enough to ensure a valid checkpoint exists. It must not create an endless stop loop.

`PostCompact` and `SessionStart` with source `compact` may be used to restore a minimal recovery pointer. The real source of truth remains the filesystem and Git, not hook-provided memory.

### 2.9 Unsupported mechanisms are removed, not simulated

If a requirement has no current documented and tested Codex mechanism, it must be removed from the active implementation contract.

It must not be:

- silently approximated;
- claimed as supported;
- hidden behind an undocumented command;
- shipped as `PARTIALLY_SUPPORTED` behavior.

The removal and reason must be recorded in `docs/OPENAI_COMPLIANCE.md`.

## 3. Authoritative sources and compatibility record

Before implementing or updating PlanAnvil, re-read current official OpenAI documentation. Do not rely only on remembered behavior, unofficial posts, or prior test results.

At minimum verify:

- GPT-5.6 prompt guidance;
- Codex skill format and skill discovery;
- `allow_implicit_invocation` behavior;
- Codex subagents and configuration;
- `AGENTS.md` discovery and precedence;
- project instruction size limits;
- hooks and their documented enforcement limits;
- sandbox and permission modes;
- Git worktree support;
- compaction and recovery mechanisms.

Record in the repository:

- each official URL used;
- verification date;
- Codex version when discoverable;
- GPT model slug used for capability tests;
- relevant compatibility notes;
- documented limitations;
- capability-test identifiers and evidence paths;
- a compliance checklist.

No model name, command, hook, field, or configuration option may be claimed unless it is confirmed in current official documentation or reproducibly capability-tested and not contradicted by official documentation.

## 4. Core product boundary

PlanAnvil must:

1. verify the repository and Git capabilities;
2. create or validate system profiles;
3. discover project instructions;
4. analyze the user goal;
5. create an isolated planning branch and worktree;
6. create one isolated run directory;
7. generate a stable `PLAN.md` contract;
8. generate atomic stage briefs and supporting artifacts;
9. independently validate the plan;
10. commit only planning and profile artifacts on the planning branch;
11. stop after plan generation and validation.

PlanAnvil must not:

- modify application code;
- write application tests;
- implement the requested feature;
- execute a generated stage;
- run migrations;
- deploy code;
- restart services;
- switch a live production system;
- create a task implementation branch;
- create an integration merge for implemented code;
- merge or push to the base branch;
- use `git stash`, `git reset`, or `git clean` to conceal or discard work;
- integrate with or export to Superpowers;
- execute another framework's workflow.

The planning branch is not an implementation branch.

## 5. Final generator behavior

After a plan is committed and independently validated, PlanAnvil must:

1. display the planning branch and commit SHA;
2. display the final plan status;
3. display critical assumptions and unknowns;
4. display the exact path of `PLAN.md`;
5. state that no implementation was executed;
6. stop.

It may ask one next-step question:

> Start a separate Codex execution run for this plan? That run will later request explicit approval before any local integration merge or live-system test.

Answering this question must not cause the current PlanAnvil run to execute the plan.

## 6. Mandatory clean-worktree precondition

PlanAnvil may begin only when the source worktree is clean.

The preflight must verify:

- no modified tracked files;
- no staged changes;
- no untracked files;
- no unresolved conflicts;
- no merge in progress;
- no rebase in progress;
- no cherry-pick in progress;
- no revert in progress;
- no bisect or other repository operation that makes planning unsafe.

When the source worktree is not clean, PlanAnvil must stop and explain the exact detected condition.

It must never:

- run `git stash`;
- run `git reset`;
- run `git clean`;
- run an equivalent destructive cleanup command;
- create a commit to conceal unrelated changes;
- move user files to another location to simulate cleanliness.

## 7. Git capability test

The Git capability test runs after the clean-worktree check and before any planning artifact is written.

### 7.1 Read-only checks

Verify:

- `git` is available;
- the directory is inside a Git repository;
- repository root can be resolved;
- current branch can be resolved, or detached-HEAD state is identified;
- `HEAD` can be resolved;
- the repository has no active unsafe operation;
- worktree status is clean;
- existing worktrees can be listed;
- remote configuration and deployment-trigger implications can be inspected without network writes.

### 7.2 Safe Git metadata probe

When permitted, perform a non-destructive metadata probe:

```text
create temporary ref pointing to current HEAD
→ verify ref
→ delete temporary ref
→ confirm branch, HEAD, index, worktree, and files are unchanged
```

The probe must use a unique namespace such as:

```text
refs/plananvil/probes/<RUN-ID>
```

It must not create a commit or switch branches.

### 7.3 Result handling

`GIT_READY` allows PlanAnvil to create the planning worktree.

`GIT_READ_ONLY` or `GIT_WRITE_RESTRICTED` stops PlanAnvil before plan generation and presents exact remediation options.

`GIT_DIRTY`, `GIT_OPERATION_IN_PROGRESS`, or `NOT_A_GIT_REPOSITORY` always stop PlanAnvil.

## 8. Project instructions

PlanAnvil and every generated execution plan must discover and enforce all applicable:

- `AGENTS.md`;
- `AGENTS.override.md`;
- configured fallback instruction filenames supported by Codex;
- nested instruction files within affected directories.

The profiler must record:

- absolute or repository-relative location;
- file hash;
- byte size;
- full-read status;
- directory scope;
- precedence;
- affected stages;
- conflicts;
- truncation risk;
- safety-critical rules.

### 8.1 Conflict-resolution rule

Use documented scope and precedence first.

Where instructions remain genuinely ambiguous, prefer the interpretation that best preserves:

- documented project intent;
- safety boundaries;
- expected user outcome;
- existing architectural conventions;
- minimal unnecessary change.

This implements the principle:

> Preserve the spirit and purpose of the project rather than exploiting a narrow literal reading.

The chosen interpretation and evidence must be logged.

An inferred interpretation must never override an explicit prohibition concerning:

- security;
- secrets;
- personal or protected data;
- destructive operations;
- production deployment;
- irreversible state changes;
- branch protection;
- legal or compliance obligations.

A remaining safety-critical conflict blocks the plan. A non-critical conflict may be resolved by best judgment with a recorded rationale.

## 9. Environment profiler

If profiles do not exist or are invalid, profile creation is mandatory before goal analysis.

The profiler creates:

```text
.pursue/SYSTEM_PROFILE.md
.pursue/SYSTEM_PROFILE.local.md
```

### 9.1 `SYSTEM_PROFILE.md`

This versioned file contains repository-safe information:

- repository identity and structure;
- languages, frameworks, and runtimes;
- dependency managers;
- build commands;
- test commands;
- linters and static-analysis tools;
- architecture overview;
- Git conventions;
- branch protection assumptions;
- general deployment rules;
- general rollback rules;
- persistent-state technologies;
- instruction-file map;
- known quality gates;
- PlanAnvil activation policy;
- plan-depth policy;
- risk thresholds;
- permitted planning artifact locations.

### 9.2 `SYSTEM_PROFILE.local.md`

This ignored local file contains machine- and environment-specific information:

- local paths;
- service names;
- process managers;
- restart commands;
- cache and queue behavior;
- deployment steps;
- branch or commit switching procedure;
- production verification procedure;
- local rollback procedure;
- infrastructure limitations;
- permission mode required for Git metadata writes;
- known CI or deployment triggers caused by pushes.

It must never contain:

- passwords;
- API keys;
- SSH private keys;
- private certificates;
- database credentials;
- copied `.env` contents;
- session cookies;
- access tokens.

### 9.3 Evidence status

Every important profile fact must use one status:

- `VERIFIED` — confirmed by a file, command, configuration, or reproducible check;
- `USER_CONFIRMED` — explicitly confirmed by the user;
- `INFERRED` — reasoned but unconfirmed;
- `UNKNOWN` — unresolved.

Verified facts must record evidence paths or commands.

### 9.4 Profile freshness

Profile validity must be based primarily on hashes of:

- all applicable instruction files;
- dependency manifests and lockfiles;
- test configuration;
- build configuration;
- quality-tool configuration;
- deployment scripts;
- migration and state-management files;
- PlanAnvil activation configuration.

Use statuses:

- `VALID`;
- `PARTIALLY_STALE`;
- `STALE`;
- `UNVERIFIABLE`;
- `VALID_WITH_UNKNOWNS`.

The local profile requires lightweight revalidation after 30 days even when repository hashes have not changed.

### 9.5 Profiler permissions

The profiler may perform read-only and demonstrably non-destructive diagnostics:

- file inspection;
- Git read operations;
- version checks;
- linting when side effects are ruled out;
- static analysis when side effects are ruled out;
- service-status reads;
- safe health checks;
- verified dry runs.

It must not:

- modify product code;
- install or update dependencies;
- run migrations;
- restart services;
- clear caches;
- switch the source worktree branch;
- mutate production data;
- run tests whose side effects cannot be ruled out.

## 10. Configurable activation policy

PlanAnvil must activate explicitly when the user invokes `$plan-anvil`.

Automatic recommendation or activation thresholds must be configured in `SYSTEM_PROFILE.md`, not hard-coded globally.

Example:

```yaml
plananvil:
  activation_policy:
    explicit_request_always: true
    implicit_invocation_allowed: false
    recommend_when:
      minimum_files: 3
      minimum_domains: 2
      public_api_change: true
      stateful_change: true
      irreversible_change: true
      migration: true
      production_procedure_required: true
      risk_at_least: HIGH
```

The profile may define a lighter or stricter boundary for a specific repository.

Ordinary coding questions and immediate fixes must not activate PlanAnvil implicitly.

## 11. Repository layout to implement

Use progressive disclosure and the native Codex skill path.

```text
PlanAnvil/
├── README.md
├── LICENSE
├── CHANGELOG.md
├── AGENTS.md
├── docs/
│   ├── IMPLEMENTATION_SPEC.md
│   ├── OPENAI_COMPLIANCE.md
│   ├── CODEX_CAPABILITY_BASELINE.md
│   ├── ARCHITECTURE.md
│   └── EXAMPLES.md
├── .agents/
│   └── skills/
│       └── plan-anvil/
│           ├── SKILL.md
│           ├── agents/
│           │   └── openai.yaml
│           ├── references/
│           │   ├── planning-contract.md
│           │   ├── profiler-contract.md
│           │   ├── git-contract.md
│           │   ├── testing-contract.md
│           │   ├── recovery-contract.md
│           │   ├── hooks-contract.md
│           │   └── openai-sources.md
│           ├── templates/
│           │   ├── PLAN.md
│           │   ├── stage-brief.md
│           │   ├── manifest.md
│           │   ├── state.md
│           │   ├── compliance.md
│           │   ├── risk-card.md
│           │   ├── checkpoint.md
│           │   ├── agent-report.md
│           │   ├── plan-review.md
│           │   └── incident-report.md
│           ├── scripts/
│           │   ├── preflight.*
│           │   ├── test-git-capabilities.*
│           │   ├── profile.*
│           │   ├── validate-profile.*
│           │   ├── map-instructions.*
│           │   ├── scaffold-run.*
│           │   ├── validate-plan.*
│           │   └── validate-agent-diff.*
│           └── tests/
│               ├── activation/
│               ├── preflight/
│               ├── git-capabilities/
│               ├── profiler/
│               ├── instructions/
│               ├── plan-generation/
│               ├── hooks/
│               ├── compaction/
│               ├── safety/
│               └── fixtures/
└── examples/
    ├── small-change/
    ├── stateful-change/
    ├── blocked-plan/
    └── git-write-restricted/
```

Keep `SKILL.md` focused on activation, boundaries, the top-level workflow, and required outputs. Move detailed rules to references, templates, and deterministic scripts.

## 12. Planning branch and worktree

After `GIT_READY`, each invocation creates an isolated planning worktree and branch:

```text
pursue/plan/<PLAN-ID>/<slug>
```

Store:

```text
SOURCE_WORKTREE
BASE_BRANCH
BASE_SHA
PLANNING_BRANCH
PLANNING_WORKTREE
```

The source worktree must remain on its original branch and `HEAD`.

The planning branch may contain only:

- `.pursue/SYSTEM_PROFILE.md` updates;
- allowed ignore-rule updates needed for `.pursue/SYSTEM_PROFILE.local.md`;
- run artifacts;
- PlanAnvil-generated documentation directly required for the plan.

It must not contain product implementation or product tests.

At completion, PlanAnvil commits planning artifacts on the planning branch. It must not push unless the user separately and explicitly requests a push and the profile confirms the push is safe.

## 13. One isolated directory per generated plan

Every invocation creates:

```text
.pursue/runs/<TIMESTAMP>_<PLAN-ID>_<SLUG>/
```

Timestamp format:

```text
YYYYMMDDTHHMMSSZ
```

Required contents:

```text
.pursue/runs/<RUN-ID>/
├── PLAN.md
├── manifest.md
├── state.md
├── compliance.md
├── stages/
│   ├── STAGE-01.md
│   ├── STAGE-02.md
│   └── ...
├── checkpoints/
├── reports/
│   ├── profiling/
│   ├── analysis/
│   ├── plan-review/
│   ├── implementation/
│   ├── verification/
│   ├── jenny/
│   └── winston-wolfe/
├── tests/
│   ├── plans/
│   ├── results/
│   └── artifacts/
├── risks/
├── diffs/
├── logs/
├── incidents/
└── final/
```

`PLAN.md` is the stable execution contract. Stage-specific details belong in `stages/*.md`.

## 14. Stable contract versus execution details

PlanAnvil must describe primarily **what must be true**, not pre-write the full implementation.

`PLAN.md` contains stable decisions and guardrails:

- outcome;
- scope;
- constraints;
- acceptance criteria;
- risk controls;
- stage boundaries;
- evidence requirements;
- Git and recovery rules.

Stage briefs contain bounded execution details:

- exact affected paths known at planning time;
- applicable instructions;
- interfaces and invariants;
- acceptance criteria;
- risks and required tests;
- commands that are already verified as stable;
- command-discovery rules for commands that depend on runtime state.

Do not include:

- full speculative production-code implementations;
- invented method signatures without repository evidence;
- stale line numbers presented as permanent truth;
- exact deployment commands not verified by the local profile;
- placeholders such as `TBD`, `TODO`, or “add appropriate tests”.

Exact code and state-dependent commands are determined during the separate execution run using the current repository state and profile.

## 15. Required `PLAN.md` contents

Every `PLAN.md` must contain:

1. plan identity and contract version;
2. separate execution-run prompt;
3. expected outcome;
4. definition of done;
5. generator stop boundary;
6. executor stop conditions;
7. scope;
8. out-of-scope items;
9. assumptions;
10. unknowns and criticality;
11. evidence sources;
12. applicable project instructions;
13. instruction-conflict resolutions;
14. system summary;
15. affected components;
16. data and state flow;
17. dependencies;
18. change classification;
19. stable stage index;
20. acceptance criteria;
21. requirement-to-stage traceability;
22. risk register;
23. risk-to-control matrix;
24. testing procedure;
25. Git procedure;
26. integration procedure;
27. production verification procedure;
28. rollback procedure;
29. context-management rules;
30. agent topology and permissions;
31. resume and reconciliation procedure;
32. plan-change log;
33. execution status model;
34. next action;
35. final-report requirements.

## 16. Atomic-stage rules

Each stage represents one logical, independently testable result.

A stage may modify multiple files only when every file is directly required for that single outcome.

Split a stage when:

- it spans independent domains;
- it changes unrelated responsibilities;
- parts need independent acceptance criteria;
- parts can be deployed or rolled back separately;
- parts have different risk profiles;
- independent commits are required;
- the outcome cannot be expressed in one short sentence.

Each stage must have:

- a stable identifier that is never renumbered;
- one-sentence outcome;
- scope and exclusions;
- affected paths or path-discovery procedure;
- applicable instruction files;
- dependencies;
- conflicts with other stages;
- acceptance criteria;
- risks;
- required tests or other controls;
- one modifier role at a time;
- independent verification;
- one coherent commit;
- one verified checkpoint.

Reordering must not change stable identifiers.

## 17. Traceability

Every important item must be traceable through stable identifiers:

```text
Requirement
→ Stage
→ Acceptance criterion
→ Risk
→ Test or other control
→ Evidence artifact
→ Verification result
```

A generated traceability table must identify:

- uncovered requirements;
- stages without a requirement;
- criteria without evidence;
- risks without controls;
- tests without linked behavior;
- public behavior without explicit user approval where required.

A critical traceability gap blocks `READY` status.

## 18. Acceptance criteria and best-effort planning

Acceptance criteria are defined before tests and implementation.

Each criterion must:

- have a stable identifier;
- be objectively verifiable where reasonably possible;
- identify its test or evidence type;
- remain inside stage scope;
- avoid subjective language without a measurable definition.

### 18.1 Non-critical ambiguity

For a non-critical ambiguity, PlanAnvil must:

- make the best supported interpretation;
- record it as `INFERRED` or `UNKNOWN`;
- state the evidence;
- state how it will be verified later;
- continue when safe.

### 18.2 Critical ambiguity

The plan cannot become `READY` when missing information prevents safe definition of:

- expected behavior;
- a critical acceptance test;
- data migration behavior;
- rollback;
- public API behavior;
- production switching;
- an irreversible operation;
- security or permission behavior.

Use:

```text
BLOCKED_BY_CRITICAL_UNKNOWN
```

Retain the partial plan and all completed analysis.

Once execution begins, acceptance criteria are frozen. A change requires a recorded reason, versioned replacement, renewed scope and risk analysis, renewed Jenny review, and retained history.

## 19. Generated execution architecture

The plan must define a separate execution run with the following roles.

### 19.1 Jim — main orchestrator

Jim manages execution but never performs technical implementation.

Jim may:

- read and update plan and state files;
- launch direct-child agents;
- enforce sequencing;
- manage checkpoints;
- evaluate quality gates;
- manage allowed branches, worktrees, and commits;
- record concise summaries;
- stop execution.

Jim must not:

- modify product code;
- write or modify tests;
- repair an implementation;
- make opportunistic technical edits;
- substitute for a technical agent;
- accept evidence produced by an unauthorized descendant.

### 19.2 Flat agent topology

Required topology:

```text
Jim
├── analysis agent
├── Jenny
├── implementation agent
├── independent verifier
└── Winston Wolfe when required
```

All technical agents are direct children of Jim.

The plan must prohibit children from spawning descendants even though Codex may technically support it.

`SubagentStart` may log the actual tree. Before every checkpoint, Jim must compare the observed tree with the authorized tree.

### 19.3 Concurrency

Only one agent may modify repository files at a time.

Read-only analysis agents may run concurrently only when:

- the profile allows it;
- they do not mutate files or external systems;
- their outputs are isolated;
- concurrency does not weaken blind review.

Jenny and the production-code implementer must never modify files concurrently.

### 19.4 File handoffs

Each agent receives a short file-based brief, not accumulated conversation history.

A dispatch contains only:

- role and stage identifier;
- brief path;
- required instruction paths;
- allowed write paths;
- report path;
- explicit stop conditions.

Full logs, diffs, and reasoning remain in artifacts.

## 20. Independent plan and implementation verification

### 20.1 Plan verification

Before `READY`, a fresh plan verifier receives:

- user goal;
- stable `PLAN.md`;
- stage briefs;
- profiles;
- instruction map;
- traceability matrix;
- risks and controls;
- validation outputs.

It must not receive the planner's reasoning or self-review report until it has written and hashed an independent conclusion.

The comparison phase then receives the planner report and checks for omissions or discrepancies.

### 20.2 Implementation verification

During the later execution run, verification is also two-phase:

1. **Blind technical review:** goal, scope, criteria, risks, base commit, diff, test evidence, and instructions, without implementer reasoning.
2. **Comparison:** immutable blind conclusion plus implementer report.

The blind artifact must not be modified during comparison.

## 21. Jenny — test specialist

Jenny is a direct child of Jim and a test-focused modifier.

Jenny receives:

- stage goal;
- acceptance criteria;
- code analysis;
- risks;
- affected components;
- system profile;
- applicable instructions;
- allowed write-path list.

Jenny must:

1. analyze the task and risks;
2. build a `risk → test/control` matrix;
3. evaluate existing coverage;
4. design missing tests;
5. create missing tests;
6. validate that tests fail for the intended reason;
7. validate test meaning and independence;
8. run the required test cycle;
9. store full artifacts;
10. return a concise structured report.

Jenny may modify only:

- test code;
- fixtures;
- mocks;
- test data;
- explicitly approved test infrastructure.

Jenny must never modify production code.

### 21.1 Jenny enforcement

Use defense in depth:

- restricted sandbox where supported;
- explicit allowlisted paths;
- `PreToolUse` path guard where supported;
- post-run diff verification;
- rejection of the phase if any unauthorized path changed.

Do not trust only the reported custom agent type. Capability tests showed that the runtime may report `agent_type: default` even when a named profile was requested.

If unauthorized changes exist, Jim must stop the phase and preserve evidence. He must not hide or erase the violation automatically.

## 22. Mandatory test cycle

Every behavior-adding implementation stage must enforce:

```text
GREEN BASELINE
→ EXPECTED RED
→ IMPLEMENTATION
→ FULL GREEN
→ INDEPENDENT VERIFICATION
```

Rules:

- relevant existing behavior must be green first;
- missing regression coverage is created before production implementation;
- new-behavior tests must fail for the intended reason;
- syntax, configuration, dependency, fixture, or infrastructure failures do not satisfy expected red;
- after implementation, new tests, targeted tests, regression tests, linting, static analysis, and profile-defined checks must pass;
- an unexpectedly green pre-implementation test requires investigation of existing behavior, test weakness, or task definition.

Stages that do not add testable software behavior must define an equivalent evidence cycle rather than fake a red test.

## 23. Risk register and adaptive depth

Risk levels:

- `LOW`;
- `MEDIUM`;
- `HIGH`.

Every risk requires:

- a test;
- another control; or
- an explicit explanation why no direct test applies.

Medium and high risks require a full card containing:

- identifier;
- level;
- description;
- source;
- affected component;
- probability;
- impact;
- detection method;
- linked criteria;
- linked tests or controls;
- mitigation;
- rollback;
- status.

High-risk changes automatically receive:

- deeper repository research;
- more explicit unknown analysis;
- additional review lenses;
- stricter evidence requirements;
- production and rollback validation;
- a user checkpoint before any irreversible or live-system action.

Jenny may increase risk. Reducing risk requires evidence, justification, and retained history.

## 24. Safe document autofix

PlanAnvil may automatically fix only changes that do not alter meaning, including:

- spelling;
- Markdown formatting;
- broken internal links;
- invalid references to existing stable identifiers;
- mechanically detectable template omissions whose content is already unambiguous.

It must request approval before changing:

- scope;
- outcome;
- public behavior;
- architecture decisions;
- risk level downward;
- acceptance criteria meaning;
- irreversible operations;
- deployment or rollback behavior.

## 25. Execution retry and strategy reset

The generated execution plan uses two strategies with three attempts each.

```text
STRATEGY-A: ATTEMPT-A1, ATTEMPT-A2, ATTEMPT-A3
STRATEGY-B: ATTEMPT-B1, ATTEMPT-B2, ATTEMPT-B3
```

After three failed attempts:

- mark Strategy A `REJECTED`;
- prohibit a fourth variation of the same approach;
- perform new high-effort analysis;
- create a materially different hypothesis;
- redo risks and tests;
- start Strategy B from the last verified checkpoint.

After six total implementation failures, stop the process.

Infrastructure-only failures do not consume an implementation attempt unless caused by the implementation.

### 25.1 Baseline restoration without hiding work

Do not use stash, reset, or clean to conceal a failed attempt.

Prefer:

- checkpoint commits;
- a new isolated attempt worktree or branch created from the last verified checkpoint;
- preservation of the failed attempt for audit;
- explicit cleanup only after user approval or documented safe retention policy.

## 26. Winston Wolfe

After both strategies fail, Jim launches a fresh read-only direct child named **Winston Wolfe**.

Winston must not modify code or perform a seventh attempt.

The incident report contains:

1. failing behavior;
2. unmet criteria;
3. both strategies;
4. why they failed;
5. confirmed facts;
6. unconfirmed hypotheses;
7. repository state;
8. rollback viability;
9. risk assessment;
10. ranked solution directions;
11. information required from the user;
12. one recommended next action.

Final failure status:

```text
BLOCKED_BY_UNRESOLVED_FAILURE
```

## 27. Main-context memory discipline

Jim's context must remain short.

Jim receives concise summaries rather than:

- raw terminal logs;
- full stack traces;
- complete diffs;
- full test output;
- long code exploration;
- lengthy implementer reasoning.

Example:

```text
Stage: STAGE-03
Phase: VERIFICATION
Result: PASS
Criteria: 6/6
Tests: 42 passed, 0 failed
Risks: 0 HIGH, 1 LOW
Agent tree: COMPLIANT
Write scope: COMPLIANT
Artifact: reports/verification/STAGE-03.md
Next action: create verified checkpoint
```

Jim reads full artifacts only for failure, blockers, high risk, conflicting reports, strategy reset, recovery, unauthorized writes, unauthorized agents, or Winston analysis.

## 28. Compaction and recovery policy

Before compaction, ensure a checkpoint contains:

- stage and phase result;
- test evidence;
- current SHA;
- branch and worktree;
- clean or explained Git status;
- open and closed risks;
- actual agent-tree audit;
- write-scope audit;
- next action;
- recovery instructions.

A `PreCompact` hook may stop compaction only when no valid checkpoint exists. Once the checkpoint exists, compaction must be allowed.

After compaction:

1. `PostCompact` records the event;
2. `SessionStart` may inject only the recovery pointer;
3. Jim reads `manifest.md`, `state.md`, the latest checkpoint, profiles, and Git state;
4. Jim reconciles actual state;
5. execution continues only on an acceptable reconciliation result.

Do not rely on conversational memory or hook context as the source of truth.

## 29. Plan changes during execution

Jim may autonomously:

- clarify descriptions;
- reorder stages without renumbering them;
- split an oversized stage using new stable identifiers;
- add missing tests;
- add risks;
- change technical implementation while preserving the approved outcome.

Jim may add a stage only when it:

- is necessary for the original goal;
- remains in the same domain;
- adds no new business feature;
- is atomic;
- has criteria, risks, tests, and a commit;
- is not irreversible.

Jim must request user approval when a change:

- adds a business objective;
- introduces an unrelated domain;
- changes public behavior or API beyond the approved requirement;
- introduces an unexpected destructive migration;
- is irreversible;
- materially changes the expected result.

## 30. Git model for execution

The generated plan requires a dedicated task branch:

```text
pursue/<PLAN-ID>/<slug>
```

Store:

```text
BASE_BRANCH
BASE_SHA
TASK_BRANCH
```

Each completed atomic stage ends in one coherent commit containing the implementation and required tests.

Jim generates concrete Git commands immediately before execution from the current profile and repository state.

Record all executed Git commands.

Never:

- force-push;
- rewrite the base branch;
- discard user work;
- push to the base branch automatically.

Hooks may block known destructive commands, but Jim must also verify postconditions and actual Git state.

## 31. Integration branch and local testing

After all automated stages pass, Jim must:

1. push the task branch only when the profile confirms that push is safe;
2. create an integration branch from the current base branch;
3. merge the task branch into the integration branch;
4. run post-merge tests;
5. push the integration branch only when explicitly allowed;
6. never push or merge to the base branch automatically.

Recommended branch:

```text
pursue/integration/<PLAN-ID>/<slug>
```

Before local integration testing or switching a live worktree, Jim must request explicit user approval.

## 32. Local production verification

The generated plan may support testing a specific integration commit on a live system only after automated verification and explicit user consent.

Before switching, store:

```text
PRODUCTION_BASE_SHA
TASK_BRANCH_SHA
INTEGRATION_BRANCH
INTEGRATION_MERGE_SHA
```

Jim presents:

- concise change summary;
- open risks;
- rollback procedure;
- a set of manual test scenarios sized by the profile;
- a request for permission.

The default number of scenarios may be 10, but the profile may require more or fewer based on risk and system complexity.

Each scenario uses:

```text
initial state > action A > action B > expected result
```

Exact switch, build, cache, restart, and rollback commands must come from `SYSTEM_PROFILE.local.md` and be revalidated immediately before use.

## 33. Stateful-change model

Classify every stage as:

- `CODE_ONLY`;
- `STATEFUL`;
- `IRREVERSIBLE`.

For stateful changes use:

```text
DISCOVER
→ BACKUP / RECOVERY POINT
→ EXPAND
→ MIGRATE
→ SWITCH
→ OBSERVE
→ CONTRACT
```

Rules:

- discover every state store and consumer;
- create and verify a technology-appropriate recovery point;
- expand backward-compatibly first;
- make migration resumable and idempotent or checkpointed;
- maintain old/new compatibility during switching where required;
- observe integrity, errors, performance, and rollback viability;
- perform destructive contraction in a separate later plan.

An irreversible step always requires separate explicit user approval.

## 34. Resume and reconciliation

The execution run must be resumable without previous conversation memory.

Initially read only:

```text
manifest.md
state.md
latest valid checkpoint
SYSTEM_PROFILE.md
SYSTEM_PROFILE.local.md
```

Then reconcile:

- repository identity;
- branch;
- `HEAD`;
- worktree status;
- active Git operations;
- applicable instructions and hashes;
- profile signatures;
- required artifacts;
- execution lock;
- agent-tree audit state;
- last write-scope audit.

Use an execution lock to prevent concurrent execution of the same plan.

Possible results:

- `EXACT_MATCH` — continue from `NEXT_ACTION`;
- `RECOVERABLE_DIRTY_STATE` — inspect and stop for a safe decision; never auto-stash/reset/clean;
- `EXTERNAL_DIVERGENCE` — analyze external changes and stop when unsafe;
- `INVALID_CHECKPOINT` — use the last fully evidenced checkpoint;
- `UNAUTHORIZED_AGENT_ACTIVITY` — reject affected evidence and stop;
- `UNAUTHORIZED_WRITE_SCOPE` — preserve evidence and stop.

Never trust `state.md` without matching Git and artifact evidence.

## 35. Status model

Plan generation statuses:

```text
PLAN_READY
BLOCKED_BY_CRITICAL_UNKNOWN
BLOCKED_BY_GIT_STATE
BLOCKED_BY_GIT_PERMISSIONS
BLOCKED_BY_INSTRUCTION_CONFLICT
PLAN_VALIDATION_FAILED
```

Execution statuses required in generated plans:

```text
READY_FOR_LOCAL_INTEGRATION_TEST
AWAITING_USER_VALIDATION
USER_ACCEPTED
USER_REJECTED
BLOCKED_BY_UNRESOLVED_FAILURE
```

`USER_ACCEPTED` does not authorize merge or push to the base branch. Base-branch integration requires a separate explicit decision.

## 36. Naming conventions

```text
Plan:             PG-YYYYMMDD-HHMMSS-XXXX
Planning branch:  pursue/plan/<PLAN-ID>/<slug>
Task branch:      pursue/<PLAN-ID>/<slug>
Integration:      pursue/integration/<PLAN-ID>/<slug>
Stage:            STAGE-01, STAGE-02, STAGE-03A
Criterion:        AC-03-01
Requirement:      REQ-03-01
Risk:             RISK-03-01
Test/control:     CTRL-03-01
Strategy:         STRATEGY-A, STRATEGY-B
Attempt:          ATTEMPT-A1 ... ATTEMPT-B3
Checkpoint:       CHECKPOINT-03-ANALYSIS, CHECKPOINT-03-VERIFIED
```

Identifiers must remain stable. Deleted identifiers are not reused.

## 37. Skill activation contract

The final description must clearly state:

- PlanAnvil generates and validates a plan but does not execute it;
- it requires a Git repository;
- it requires a clean source worktree;
- it tests Git metadata permissions before writing;
- it creates or validates system profiles;
- activation thresholds are repository-configurable;
- it creates versioned planning artifacts on an isolated planning branch;
- it is not for implementing an existing plan or making an immediate fix;
- it has no Superpowers integration.

Implicit invocation must be disabled.

## 38. Required tests for PlanAnvil

### 38.1 Activation

- native discovery from `.agents/skills`;
- explicit `$plan-anvil` activation;
- implicit invocation disabled;
- ordinary code question does not activate;
- immediate implementation request does not bypass plan-only behavior;
- execution of an existing plan does not activate the generator.

### 38.2 Preflight

- clean repository;
- modified file;
- staged change;
- untracked file;
- conflict;
- merge, rebase, cherry-pick, revert, or bisect state;
- no use of stash/reset/clean.

### 38.3 Git capabilities

- `GIT_READY`;
- Git unavailable;
- not a repository;
- metadata write denied;
- safe temporary-ref probe;
- planning worktree isolation;
- source branch and `HEAD` unchanged;
- no product files on planning branch.

### 38.4 Profiling

- no profiles;
- missing local profile;
- stale profile;
- changed instruction files;
- changed test configuration;
- unknown facts;
- attempted secret capture;
- activation-policy creation;
- missing critical deployment or rollback information.

### 38.5 Instructions

- root instruction discovery;
- nested override discovery;
- scope and precedence;
- nested instructions not auto-loaded merely from discussed paths;
- truncation by `project_doc_max_bytes`;
- explicit full-file read;
- ambiguous conflict resolved by project intent;
- explicit safety prohibition never overridden.

### 38.6 Plan generation

- small change below configured recommendation threshold;
- explicit invocation for a small change;
- large feature;
- multi-domain request;
- missing tests;
- stateful change;
- irreversible proposal;
- incomplete non-critical requirements handled best-effort;
- critical unknown blocks `PLAN_READY`;
- stable IDs survive reorder and split;
- requirement-to-test traceability.

### 38.7 Plan-only safety

- generator never modifies product code;
- generator never writes product tests;
- generator never executes a stage;
- no migration or deployment;
- no base-branch push or merge;
- planning artifacts only;
- exact stop token or equivalent observable stop state after validation.

### 38.8 Hooks and write boundaries

- allowed test-path write;
- forbidden production-path writes through multiple tool forms;
- destructive Git command blocking;
- post-diff catches a deliberately bypassed or unobserved write;
- hooks disabled still leave post-diff validation effective;
- custom agent-type mismatch does not weaken enforcement.

### 38.9 Agent topology

- flat authorized topology;
- nested agent capability probe;
- unauthorized descendant detected;
- unauthorized descendant result rejected;
- `SubagentStart` used for audit, not blocking;
- one file-modifying agent at a time.

### 38.10 Compaction and recovery

- manual compaction delayed until checkpoint;
- automatic compaction delayed until checkpoint;
- no permanent auto-compaction stop loop;
- `PostCompact` event recorded;
- `SessionStart(compact)` injects recovery pointer;
- state reconstructed from files and Git;
- invalid checkpoint rejected.

### 38.11 Generated execution contract

- Jim cannot modify code or tests;
- Jenny cannot modify production code;
- blind verification exists and remains immutable;
- two-strategy retry model;
- Winston after six failures;
- task and integration branch workflow;
- explicit user approval before live test;
- irreversible changes blocked for approval.

## 39. Implementation acceptance criteria

PlanAnvil is complete only when:

1. it follows the current native Codex skill format;
2. it is installed under `.agents/skills/plan-anvil`;
3. implicit invocation is disabled;
4. `SKILL.md` remains narrow and uses progressive disclosure;
5. preflight blocks dirty repositories without hiding changes;
6. the Git capability test returns explicit statuses;
7. planning branch and worktree isolation are verified;
8. the source worktree remains unchanged;
9. both profiles are created and validated;
10. the local profile is ignored and secret-safe;
11. activation policy is stored in the profile;
12. every invocation creates an isolated run directory;
13. `PLAN.md` is a stable contract and stages use separate briefs;
14. stage and traceability identifiers remain stable;
15. non-critical unknowns use best effort;
16. critical unknowns block readiness;
17. plans define the flat Jim-centered topology;
18. plans do not rely on `max_depth` for security;
19. `SubagentStart` is audit-only;
20. write restrictions use defense in depth;
21. post-agent diffs are mandatory;
22. risk-driven red/green testing is enforced;
23. blind plan verification is implemented;
24. the 2 × 3 retry model is generated;
25. Winston cannot modify code;
26. checkpoint, compact, recovery, and reconciliation are implemented;
27. task and integration branch isolation is generated;
28. live testing and rollback require explicit approval;
29. stateful plans are technology agnostic;
30. no Superpowers integration exists;
31. unsupported Codex mechanisms are absent from active behavior;
32. all required tests pass;
33. `OPENAI_COMPLIANCE.md` contains no unresolved contradiction;
34. README explains installation, activation, outputs, safety, permissions, and examples.

## 40. Required implementation workflow

The implementing agent must:

1. open the PlanAnvil repository;
2. read repository instructions and this specification;
3. verify a clean worktree;
4. create a dedicated implementation branch;
5. verify current official OpenAI documentation;
6. read `CODEX_CAPABILITY_BASELINE.md` and reproduce critical tests where needed;
7. write architecture and compliance notes first;
8. implement the minimal native skill skeleton;
9. implement preflight and Git capability tests;
10. implement profiles and instruction mapping;
11. implement templates and stable identifiers;
12. implement optional hooks as defense in depth;
13. implement mandatory postcondition validators;
14. implement plan validation and blind review;
15. implement compaction recovery workflow;
16. implement automated and reproducible tests;
17. run the complete quality gate;
18. review generated examples;
19. confirm no secrets or machine-specific paths are committed;
20. confirm no product code can be modified by the generator;
21. commit in coherent units;
22. push only the implementation branch when explicitly authorized;
23. provide a final report with evidence and exact next steps.

## 41. Non-goals

PlanAnvil does not:

- execute the generated plan;
- implement product code or tests;
- automatically merge or push the base branch;
- automatically elevate Codex permissions;
- create a staging environment;
- guarantee reversibility of inherently irreversible actions;
- manage secrets;
- ignore explicit safety instructions in favor of inferred intent;
- allow parallel code modification;
- rely solely on hooks for security;
- rely solely on `agents.max_depth` for topology control;
- use `SubagentStart` as a start blocker;
- permanently block compaction after the context threshold is exceeded;
- integrate with Superpowers;
- export Superpowers-compatible plans;
- run destructive tests on production;
- make the final business-acceptance decision.

---

## Handoff instruction to the implementing agent

Treat this document as the authoritative product contract.

Where it conflicts with current official OpenAI documentation:

1. stop the affected implementation work;
2. reproduce the capability with an isolated test when safe;
3. follow current documented behavior;
4. record the conflict and evidence in `docs/OPENAI_COMPLIANCE.md`;
5. preserve the product intent using a documented and tested mechanism;
6. remove any requirement that still cannot be implemented safely.

Do not silently omit, simulate, or overstate a capability.
