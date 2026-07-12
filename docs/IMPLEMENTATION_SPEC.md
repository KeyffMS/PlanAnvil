# PlanAnvil — Implementation Specification

> **Repository:** https://github.com/KeyffMS/PlanAnvil  
> **Document purpose:** provide the implementing agent with a complete and unambiguous product contract.  
> **Important:** this document describes what must be built. It is not the final `SKILL.md`.

## 1. Product goal

Build **PlanAnvil**, a Codex skill whose only responsibility is to generate a rigorous, test-driven, auditable implementation plan for a software-engineering goal.

PlanAnvil must **create the plan but never execute it**. The generated plan must contain a complete execution prompt and all instructions required by a later Codex run to carry out the work autonomously.

The output must be suitable for long-running repository work with:

- strict Git isolation;
- mandatory project-instruction discovery;
- environment profiling;
- small atomic stages;
- risk-driven testing;
- independent verification;
- resumable state;
- production-safe branch testing;
- explicit rollback procedures;
- minimal memory usage in the main orchestrator context.

## 2. Authoritative sources

Before implementing PlanAnvil, re-read the current official OpenAI documentation. Do not rely on remembered behavior, unofficial posts, or assumptions.

At minimum verify:

- GPT-5.6 prompt guidance:  
  https://developers.openai.com/api/docs/guides/prompt-guidance-gpt-5p6
- Codex skills documentation;
- Codex subagent documentation;
- `AGENTS.md` instruction hierarchy;
- Codex configuration and context-management documentation;
- any official documentation governing the command or mechanism used to execute a generated long-running plan.

Record in the repository:

- every official URL used;
- verification date;
- relevant compatibility notes;
- unsupported or undocumented assumptions;
- a compliance checklist.

The implementation must not claim support for a model name, command, hook, or configuration option unless it is confirmed in current official documentation.

## 3. Core boundary

PlanAnvil must:

1. inspect the repository and its profiles;
2. analyze the user goal;
3. create a structured plan directory;
4. generate a complete `PLAN.md` execution contract;
5. generate supporting manifests, state templates, risk templates, test templates, and compliance records;
6. stop after plan generation and validation.

PlanAnvil must not:

- modify application code;
- implement the requested feature;
- run migrations;
- deploy code;
- execute the generated plan;
- merge the feature into the base branch;
- hide, stash, reset, clean, or commit unrelated user changes.

## 4. Mandatory clean-worktree precondition

PlanAnvil may start only when the repository worktree is clean.

The preflight must verify:

- no modified tracked files;
- no staged changes;
- no untracked files;
- no unresolved conflicts;
- no merge in progress;
- no rebase in progress;
- no cherry-pick in progress;
- no revert in progress.

When the repository is not clean, PlanAnvil must stop and explain the detected condition. It must not run `git stash`, `git reset`, `git clean`, or create a commit to conceal the state.

## 5. `AGENTS.md` is mandatory and authoritative

PlanAnvil and every generated execution plan must require discovery and enforcement of all applicable:

- `AGENTS.md`;
- `AGENTS.override.md`;
- nested instruction files supported by current Codex documentation.

The profiler must record:

- file locations;
- scope by directory;
- precedence;
- conflicts;
- instructions relevant to each planned stage.

The generated plan must require each fresh subagent to re-read the instructions applicable to the files it will inspect or modify.

If the plan conflicts with an applicable project instruction, the project instruction wins. The conflict must be logged and the plan must be adjusted or stopped.

## 6. Environment profiler

PlanAnvil requires a profiler component or companion skill.

If the profiles do not exist, profile creation is mandatory before goal analysis begins.

The profiler creates:

```text
.pursue/SYSTEM_PROFILE.md
.pursue/SYSTEM_PROFILE.local.md
```

### 6.1 `SYSTEM_PROFILE.md`

This file is versioned in Git and contains information safe for repository storage:

- repository structure;
- languages, frameworks, and runtimes;
- dependency managers;
- build commands;
- test commands;
- linters and static-analysis tools;
- architecture overview;
- Git conventions;
- general deployment rules;
- general rollback rules;
- persistent-state technologies;
- `AGENTS.md` map;
- known quality gates.

### 6.2 `SYSTEM_PROFILE.local.md`

This file is local and must be ignored by Git. It contains machine- and production-specific information:

- local paths;
- service names;
- process managers;
- restart commands;
- cache and queue behavior;
- deployment steps;
- branch/commit switching procedure;
- production verification procedure;
- local rollback procedure;
- infrastructure limitations.

It must never contain secrets, passwords, API keys, SSH keys, private certificates, database credentials, or copied `.env` contents.

### 6.3 Evidence status

Every important profile fact must have one status:

- `VERIFIED` — confirmed by a file, command, or configuration;
- `USER_CONFIRMED` — explicitly confirmed by the user;
- `INFERRED` — reasoned but unconfirmed;
- `UNKNOWN` — unresolved.

Verified facts must record their evidence source.

### 6.4 Profile freshness

Profile validity must be based primarily on signatures or hashes of relevant files, including:

- all applicable instruction files;
- dependency manifests and lockfiles;
- test configuration;
- build configuration;
- quality-tool configuration;
- deployment scripts;
- migration/state-management files.

Use statuses such as:

- `VALID`;
- `PARTIALLY_STALE`;
- `STALE`;
- `UNVERIFIABLE`;
- `VALID_WITH_UNKNOWNS`.

The local profile requires a lightweight revalidation after 30 days even when repository signatures have not changed.

### 6.5 Profiler permissions

The profiler may perform read-only and demonstrably non-destructive diagnostics:

- file inspection;
- Git read operations;
- version checks;
- linting;
- static analysis;
- service-status reads;
- safe health checks;
- verified dry runs.

It must not:

- modify product code;
- install or update dependencies;
- run migrations;
- restart services;
- clear caches;
- switch branches during profiling;
- mutate production data;
- run tests whose side effects cannot be ruled out.

## 7. Repository layout to implement

Create a clear skill repository with progressive disclosure. The implementing agent may refine names only when required by current official Codex skill conventions.

Recommended structure:

```text
PlanAnvil/
├── README.md
├── LICENSE
├── CHANGELOG.md
├── AGENTS.md
├── docs/
│   ├── IMPLEMENTATION_SPEC.md
│   ├── OPENAI_COMPLIANCE.md
│   ├── ARCHITECTURE.md
│   └── EXAMPLES.md
├── skills/
│   └── plan-anvil/
│       ├── SKILL.md
│       ├── references/
│       │   ├── planning-contract.md
│       │   ├── profiler-contract.md
│       │   ├── git-contract.md
│       │   ├── testing-contract.md
│       │   ├── recovery-contract.md
│       │   └── openai-sources.md
│       ├── templates/
│       │   ├── PLAN.md
│       │   ├── manifest.md
│       │   ├── state.md
│       │   ├── compliance.md
│       │   ├── risk-card.md
│       │   ├── checkpoint.md
│       │   ├── agent-report.md
│       │   └── incident-report.md
│       ├── scripts/
│       │   ├── preflight.*
│       │   ├── profile.*
│       │   ├── validate-profile.*
│       │   ├── scaffold-run.*
│       │   └── validate-plan.*
│       └── tests/
│           ├── activation/
│           ├── preflight/
│           ├── profiler/
│           ├── plan-generation/
│           ├── safety/
│           └── fixtures/
└── examples/
    ├── small-change/
    ├── stateful-change/
    └── blocked-plan/
```

Do not add complexity without a concrete purpose. Keep `SKILL.md` focused and move detailed contracts into references and templates.

## 8. One isolated directory per generated plan

Every invocation creates a separate timestamped run directory:

```text
.pursue/runs/<TIMESTAMP>_<PLAN-ID>_<SLUG>/
```

Timestamp format:

```text
YYYYMMDDTHHMMSSZ
```

Recommended contents:

```text
.pursue/runs/<RUN-ID>/
├── PLAN.md
├── manifest.md
├── state.md
├── compliance.md
├── checkpoints/
├── reports/
│   ├── analysis/
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

`PLAN.md` is the execution source of truth. Detailed logs and reports belong in supporting files, with short references in `PLAN.md`.

## 9. Required `PLAN.md` contents

Every generated plan must contain at least:

1. plan identity;
2. execution prompt;
3. expected outcome;
4. definition of done;
5. stop conditions;
6. scope;
7. out-of-scope items;
8. assumptions;
9. unknowns;
10. evidence sources;
11. applicable project instructions;
12. system summary;
13. affected components;
14. data/state flow;
15. dependencies;
16. change classification;
17. atomic stages;
18. acceptance criteria;
19. risk register;
20. risk-to-test matrix;
21. testing procedure;
22. Git procedure;
23. production verification procedure;
24. rollback procedure;
25. context-management rules;
26. resume/reconciliation procedure;
27. plan-change log;
28. execution status model;
29. next action;
30. final-report requirements.

## 10. Atomic-stage rules

Each stage must represent one small logical change, preferably centered on one:

- class;
- service;
- component;
- module;
- domain;
- endpoint;
- business flow;
- coherent UI element.

A stage may modify multiple files only when every file is directly required for that single logical outcome.

Split a stage when:

- it spans multiple domains;
- it changes independent responsibilities;
- it needs independent acceptance criteria;
- parts can be deployed or rolled back separately;
- parts have different risk profiles;
- multiple independent commits are required;
- the goal cannot be summarized in one short sentence.

Each stage must have its own:

- analysis;
- acceptance criteria;
- risks;
- tests;
- independent verification;
- commit;
- checkpoint.

## 11. Acceptance criteria

Acceptance criteria are mandatory and must be defined before tests and implementation.

Each criterion must:

- have a stable identifier;
- be objectively verifiable;
- identify its test or evidence;
- remain inside stage scope.

Once implementation begins, criteria are frozen. Any change requires:

- a recorded reason;
- versioned replacement;
- renewed scope analysis;
- renewed risk analysis;
- renewed Jenny review;
- retained history.

## 12. Generated execution architecture

The plan must define the following autonomous execution roles.

### 12.1 Jim — main orchestrator

Jim manages the process but never performs technical implementation.

Jim may:

- read and update plan/state files;
- launch subagents;
- enforce sequencing;
- manage checkpoints;
- evaluate quality gates;
- manage Git branches and commits;
- record concise summaries;
- stop the process when required.

Jim must not:

- modify product code;
- write tests;
- repair implementation;
- perform opportunistic edits;
- substitute for a technical subagent.

### 12.2 Fresh stage agents

Each stage uses fresh, sequential agents for:

1. analysis;
2. implementation;
3. independent verification.

Only one technical agent may work at a time. No concurrent code modification is allowed.

### 12.3 Independent verifier

Verification is two-phase:

1. **Blind technical review:** receives goal, scope, criteria, risks, risk-test matrix, base commit, diff, test results, and applicable instructions, but not the implementer’s reasoning.
2. **Comparison phase:** after recording an independent conclusion, receives the implementer report and checks for discrepancies or omitted effects.

## 13. Jenny — test specialist

Jenny is a test-focused nested agent.

Jenny receives:

- stage goal;
- acceptance criteria;
- code analysis;
- risks;
- affected components;
- system profile;
- applicable instructions.

Jenny must:

1. analyze the task;
2. analyze risks;
3. build a `risk → test` matrix;
4. evaluate existing coverage;
5. design missing tests;
6. create missing tests;
7. validate that the tests themselves are meaningful;
8. run the required test cycle;
9. store full artifacts;
10. return a concise structured report.

Jenny may modify only test code, fixtures, mocks, test data, and test infrastructure. Jenny must never modify production code.

The implementation must use only agent-nesting capabilities that are currently documented by OpenAI. Verify required depth and configuration before encoding them.

## 14. Mandatory test cycle

Every implementation stage must enforce:

```text
GREEN BASELINE
→ EXPECTED RED
→ IMPLEMENTATION
→ FULL GREEN
```

Rules:

- Existing relevant behavior must be green before the change.
- Missing regression coverage must be created before production implementation.
- New-behavior tests must fail for the intended reason before implementation.
- A test failing because of syntax, configuration, dependency, fixture, or infrastructure errors does not satisfy expected red.
- After implementation, new tests, targeted tests, regression tests, linting, static analysis, and profile-defined quality checks must be green.
- If a new test is already green before implementation, Jenny must determine whether the feature already exists, the test is weak, or the task definition is wrong.

## 15. Risk register

Risk levels:

- `LOW`;
- `MEDIUM`;
- `HIGH`.

Low risks may use a compact record.

Medium and high risks require a full card containing:

- identifier;
- level;
- description;
- source;
- affected component;
- probability;
- impact;
- detection method;
- linked tests;
- mitigation;
- rollback;
- status.

Every risk must have a test, another control, or an explicit explanation for why no test applies.

Jenny may increase a risk level. Reducing a risk level requires evidence, justification, and retained history.

## 16. Autofix and strategy reset

A failed stage may use two strategies with three attempts each.

### Strategy A

```text
ATTEMPT-A1
ATTEMPT-A2
ATTEMPT-A3
```

These are short tactical fixes within the original approach.

After three failures:

- mark Strategy A `REJECTED`;
- forbid a fourth variation of the same approach;
- run a new high-effort analysis;
- create a materially different solution hypothesis;
- redo risks and tests;
- restore a safe stage baseline before Strategy B.

### Strategy B

```text
ATTEMPT-B1
ATTEMPT-B2
ATTEMPT-B3
```

Strategy B must represent a genuinely different diagnosis or implementation design.

After six total failures, stop the entire process.

Infrastructure-only test failures do not consume an implementation attempt unless caused by the implementation itself. They must still be recorded.

## 17. Winston Wolfe — damage-control reporter

After both strategies fail, Jim launches a fresh read-only agent named **Winston Wolfe**.

Winston must not modify code or perform a seventh attempt.

Winston produces a clear incident report containing:

1. what is failing;
2. which criteria remain unmet;
3. both attempted strategies;
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

## 18. Main-context memory discipline

The main orchestrator context must remain short.

Jim should receive concise structured summaries rather than:

- raw terminal logs;
- full stack traces;
- complete diffs;
- complete test output;
- long code exploration;
- lengthy implementer reasoning.

Detailed artifacts belong in the run directory.

Jim reads full artifacts only for:

- `FAIL`;
- `BLOCKED`;
- `INCONCLUSIVE`;
- high risk;
- conflicting agent reports;
- strategy reset;
- recovery/reconciliation;
- Winston Wolfe analysis.

Example summary:

```text
Stage: STAGE-03
Phase: VERIFICATION
Result: PASS
Criteria: 6/6
Tests: 42 passed, 0 failed
Risks: 0 HIGH, 1 LOW
Artifact: reports/verification/STAGE-03.md
Next action: create stage commit
```

## 19. Context compaction policy

The generated plan must prevent uncontrolled automatic compaction of Jim’s main context when current official Codex capabilities permit it.

Manual, controlled compaction is allowed only after a completed stage and a complete checkpoint containing:

- stage result;
- test evidence;
- current SHA;
- Git state;
- open/closed risks;
- next action;
- recovery instructions.

After compaction, Jim must re-read the plan, state, checkpoint, profiles, and actual Git state before continuing.

Do not hard-code an undocumented hook, command, or configuration option. Implement this policy only with currently documented mechanisms and explain any platform limitation.

## 20. Plan changes during execution

Jim may autonomously:

- clarify descriptions;
- reorder stages;
- split an oversized stage;
- add missing tests;
- add risks;
- change technical implementation without changing the outcome.

Jim may add a new stage only when it:

- is necessary for the original goal;
- remains in the same domain;
- adds no new business feature;
- is atomic;
- has its own criteria, risks, tests, and commit;
- is not irreversible.

Jim must stop for user approval when a change:

- adds a new business objective;
- introduces a new unrelated domain;
- changes public API beyond the original requirement;
- introduces an unexpected destructive migration;
- is irreversible;
- materially changes the expected result.

## 21. Git model

Every versioned change requires a dedicated branch.

### 21.1 Feature-plan branch

```text
pursue/<PLAN-ID>/<slug>
```

Store:

```text
BASE_BRANCH
BASE_SHA
```

Each completed atomic stage ends in one coherent commit containing implementation and its required tests.

### 21.2 Profile branch

Use a profile branch when profiling changes versioned files:

```text
pursue/profile/<TIMESTAMP>-system-profile
```

A local ignored profile alone does not require a branch when no versioned file changes.

### 21.3 Git commands

The plan must describe logical Git procedures. Jim generates concrete commands immediately before execution using the current profile, current branch, remote configuration, and worktree state.

Record all executed Git commands in artifacts.

Never force-push, rewrite the base branch, or discard user work.

## 22. Task and integration branches

After all automated stages pass, Jim must:

1. push the task branch;
2. create an integration branch from the current base branch;
3. merge the task branch into the integration branch;
4. run post-merge tests;
5. push the integration branch;
6. never push changes to the base branch automatically.

Recommended integration branch:

```text
pursue/integration/<PLAN-ID>/<slug>
```

Automatic branch push is allowed only when the system profile confirms that it will not trigger unsafe deployment or workflows.

## 23. Local production verification

The user may have no staging environment and may edit the live production worktree directly.

The plan must support testing a specific integration commit on the live system only after automated verification and explicit user consent.

Before switching, store:

```text
PRODUCTION_BASE_SHA
TASK_BRANCH_SHA
INTEGRATION_BRANCH
INTEGRATION_MERGE_SHA
```

Jim must present:

- concise change summary;
- open risks;
- rollback procedure;
- exactly 10 manual test scenarios;
- a request for permission to switch the live system.

Each manual scenario uses:

```text
initial state > action A > action B > expected result
```

The 10 scenarios must cover the primary flow, errors, regressions, compatibility, medium/high risks, permissions, edge data, failure behavior, and the most important user journey.

The exact branch/commit switch, build, cache, service-restart, and rollback commands must come from `SYSTEM_PROFILE.local.md`.

## 24. Stateful-change model

PlanAnvil must be storage-technology agnostic.

Classify every stage as:

- `CODE_ONLY`;
- `STATEFUL`;
- `IRREVERSIBLE`.

For any stateful change use:

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

- discover all state stores and consumers;
- create and verify a technology-appropriate recovery point;
- introduce backward-compatible expansion first;
- make migration resumable and idempotent or checkpointed;
- maintain old/new compatibility during switching when needed;
- observe integrity, errors, performance, and rollback viability;
- perform destructive contraction only in a separate later plan.

This applies to databases, document stores, key-value stores, files, object storage, caches, queues, streams, indexes, configuration stores, and external stateful APIs.

An irreversible step requires explicit user approval and may not proceed autonomously.

## 25. Resume and reconciliation

The generated plan must be resumable without relying on previous conversational memory.

On resume, Jim initially reads only:

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
- worktree;
- active Git operations;
- applicable instructions;
- profile signatures;
- required artifacts;
- execution lock.

Use an execution lock to prevent concurrent runs of the same plan.

Possible results:

- `EXACT_MATCH` — continue from `NEXT_ACTION`;
- `RECOVERABLE_DIRTY_STATE` — inspect without automatic reset/clean/stash;
- `EXTERNAL_DIVERGENCE` — analyze external changes and stop if unsafe;
- `INVALID_CHECKPOINT` — return to the last fully evidenced checkpoint.

Never trust `state.md` without matching Git and artifact evidence.

## 26. Final status model

Use at least:

```text
READY_FOR_LOCAL_INTEGRATION_TEST
AWAITING_USER_VALIDATION
USER_ACCEPTED
USER_REJECTED
BLOCKED_BY_UNRESOLVED_FAILURE
```

`USER_ACCEPTED` completes the plan but does not authorize merge or push to the base branch. Final base-branch integration requires a separate explicit user decision.

## 27. Naming conventions

Recommended identifiers:

```text
Plan:        PG-YYYYMMDD-HHMMSS-XXXX
Task branch: pursue/<PLAN-ID>/<slug>
Integration: pursue/integration/<PLAN-ID>/<slug>
Profile:     pursue/profile/<TIMESTAMP>-system-profile
Stage:       STAGE-01, STAGE-02, STAGE-03.01
Criterion:   AC-03-01
Risk:        RISK-03-01
Test:        TEST-03-01
Strategy:    STRATEGY-A, STRATEGY-B
Attempt:     ATTEMPT-A1 ... ATTEMPT-B3
Checkpoint:  CHECKPOINT-03-ANALYSIS, CHECKPOINT-03-VERIFIED
```

## 28. Skill activation contract

PlanAnvil should activate explicitly, not for ordinary coding questions.

Its final skill description must clearly state:

- it generates a plan but does not execute it;
- it requires a Git repository;
- it requires a clean worktree;
- it creates or validates system profiles;
- it creates versioned planning artifacts;
- it is not for implementing an existing plan or making an immediate code fix.

## 29. Required tests for PlanAnvil itself

Implement automated or reproducible tests for:

### Activation

- explicit planning request activates it;
- ordinary code question does not;
- immediate implementation request does not unless the user explicitly requests a PlanAnvil plan;
- execution of an existing plan does not activate the generator.

### Preflight

- clean repository;
- modified file;
- staged change;
- untracked file;
- merge/rebase/cherry-pick/revert state;
- conflict state.

### Profiling

- no profiles;
- missing local profile;
- stale profile;
- changed instruction files;
- changed test configuration;
- unknown facts;
- attempted secret capture.

### Plan generation

- small change;
- large feature;
- multi-domain request;
- missing tests;
- stateful change;
- irreversible proposal;
- incomplete requirements;
- conflict with project instructions.

### Structure

- unique run directory;
- valid timestamp;
- complete manifest;
- complete `PLAN.md` sections;
- valid identifiers;
- execution prompt;
- stop conditions;
- supporting artifact links.

### Safety

- generator never modifies product code;
- no destructive Git cleanup;
- no secret persistence;
- no undocumented OpenAI mechanism is asserted;
- no base-branch push;
- no force-push.

### Generated execution contract

- Jim cannot modify code/tests;
- Jenny cannot modify production code;
- independent blind verification exists;
- one technical agent at a time;
- concise main-context summaries;
- resume reconciliation;
- two-strategy autofix;
- Winston after six failures;
- task and integration branch workflow;
- 10 manual test scenarios.

## 30. Implementation acceptance criteria

The implementing agent may consider PlanAnvil complete only when:

1. the skill follows current official Codex skill format;
2. `SKILL.md` has correct metadata and narrow activation rules;
3. detailed behavior is split into references/templates rather than bloating `SKILL.md`;
4. preflight blocks dirty repositories safely;
5. profiler creates and validates both profiles;
6. local profile is ignored and secret-safe;
7. each invocation creates an isolated run directory;
8. generated `PLAN.md` contains every required contract section;
9. generated plans define Jim, Jenny, verification agents, and Winston correctly;
10. generated plans enforce atomic stages and acceptance criteria;
11. generated plans enforce risk-driven red/green testing;
12. generated plans enforce the 2 × 3 autofix model;
13. generated plans preserve short main-orchestrator context;
14. generated plans support safe checkpoints and resume reconciliation;
15. generated plans implement task/integration branch isolation;
16. generated plans support user-approved live integration testing and rollback;
17. stateful plans are technology agnostic;
18. all PlanAnvil tests pass;
19. OpenAI compliance documentation has no known unresolved contradiction;
20. README explains installation, activation, outputs, safety boundaries, and examples.

## 31. Required implementation workflow

The implementing agent must:

1. clone or open https://github.com/KeyffMS/PlanAnvil;
2. read repository instructions and this specification;
3. verify a clean worktree;
4. create a dedicated implementation branch;
5. verify current official OpenAI documentation;
6. write the architecture and compliance notes first;
7. implement the minimal valid skill skeleton;
8. implement templates and profile contracts;
9. implement safe helper scripts;
10. implement tests;
11. run the complete quality gate;
12. review all generated examples;
13. confirm no secrets or machine-specific paths are committed;
14. commit in coherent units;
15. push only the implementation branch;
16. provide a final report with test evidence, known limitations, and exact next steps.

## 32. Non-goals

PlanAnvil does not:

- execute the generated plan;
- automatically merge to the base branch;
- automatically push the base branch;
- create a staging environment;
- guarantee reversibility of inherently irreversible actions;
- manage secrets;
- override project instructions;
- permit parallel code modification;
- run destructive tests on production;
- make the final business-acceptance decision for the user.

---

## Handoff instruction to the implementing agent

Treat this document as the product contract for the first implementation of PlanAnvil.

Where this specification conflicts with current official OpenAI documentation, follow the official documentation, record the conflict in `docs/OPENAI_COMPLIANCE.md`, and preserve the product intent using a documented supported mechanism.

Do not silently omit a requirement. Mark anything that cannot be implemented with current documented Codex capabilities as `BLOCKED`, `PARTIALLY_SUPPORTED`, or `REQUIRES_USER_CONFIGURATION`, and explain the exact reason.