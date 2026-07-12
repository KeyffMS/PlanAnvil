# PlanAnvil — Implementation Specification

> **Contract version:** 2.0  
> **Status:** authoritative implementation contract  
> **Target:** native OpenAI Codex skill  
> **Core boundary:** PlanAnvil generates and validates an implementation plan. It never executes that plan.

## 1. Product goal

PlanAnvil converts a software-engineering goal into a rigorous, test-driven and auditable implementation contract for a separate later Codex run.

A generated plan must support:

- strict Git isolation;
- explicit discovery of project instructions;
- repository and environment profiling;
- atomic and independently verifiable stages;
- acceptance criteria defined before implementation;
- risk-driven tests and controls;
- blind independent plan review;
- resumable file-based state;
- explicit integration, production-verification and rollback procedures;
- minimal dependence on conversational memory.

PlanAnvil is not a coding agent, executor, task manager or wrapper around another development framework.

## 2. Authority and normative language

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

The PlanAnvil runtime MUST:

1. inspect the source repository without changing it;
2. verify Git state and required Git capabilities;
3. create an isolated planning branch and planning worktree;
4. create or validate repository and local profiles inside the planning worktree;
5. discover all applicable project instructions;
6. analyze the goal and repository evidence;
7. generate `PLAN.md`, stage briefs and machine-readable control artifacts;
8. run deterministic validation;
9. run a fresh blind plan review;
10. commit only planning artifacts on the planning branch;
11. report the planning branch, commit, plan path, assumptions, unknowns and final status;
12. stop.

The runtime MUST NOT:

- modify application code;
- create or modify application tests;
- execute any generated implementation stage;
- create a task implementation branch;
- run migrations, deploy or restart services;
- switch a live system;
- create an implementation integration merge;
- merge or push to the base branch;
- use `git stash`, `git reset` or `git clean` to hide or discard work;
- start the future execution orchestrator;
- begin execution after a follow-up approval in the same run.

### 3.2 Generated execution contract

The following exist only as requirements written into the generated plan:

- Jim, the later execution orchestrator;
- Jenny, the later test specialist;
- implementation and verification agents;
- Winston Wolfe;
- task and integration branches;
- red/green implementation cycles;
- the two-strategy retry model;
- local integration and live-system verification.

PlanAnvil may use separate read-only agents to analyze or review a plan. Those agents are not the future execution roles.

A validator MUST reject an implementation or plan that conflates the generator run with the later execution run.

## 4. Implementation platform

The first production implementation MUST use:

- Python 3.11 or newer;
- Python standard library only for core deterministic scripts;
- Git 2.30 or newer;
- UTF-8 files;
- JSON as canonical machine state;
- Markdown as the human-readable contract and report format.

Supported systems are Linux, macOS and Windows with Python and Git installed.

Hook commands MUST define Windows and POSIX forms where they differ. Shell wrappers may exist, but Python entry points are canonical.

The implementation MUST NOT require elevated privileges, `sudo`, network access for local validation, installation of project dependencies merely to generate a plan, or undocumented Codex mechanisms.

Missing prerequisites produce an explicit blocking status and remediation.

## 5. Native Codex installation

The canonical repository skill location is:

```text
.agents/skills/plan-anvil/
```

The skill metadata MUST contain:

```yaml
policy:
  allow_implicit_invocation: false
```

PlanAnvil activates only after an explicit request such as `$plan-anvil`.

Repository-specific recommendation thresholds may be stored in a profile, but must never cause implicit activation.

The first release is a repository skill. Plugin packaging is optional and outside v1.

## 6. Generator lifecycle

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

No profile is written before the planning worktree exists. All generated profiles and plan files are created inside that worktree. The source worktree remains on its original branch and commit and its filesystem remains unchanged.

When a user supplies a planning branch and linked worktree because Codex cannot write Git metadata, PlanAnvil validates them and starts at profile creation.

## 7. Source preflight

Preflight MUST be read-only and verify:

- Git exists;
- the current directory is inside a Git repository;
- repository root and `HEAD` are resolvable;
- there are no modified, staged or untracked files;
- there are no conflicts;
- no merge, rebase, cherry-pick, revert, bisect or equivalent unsafe operation is active;
- linked worktrees can be listed.

Preflight must not create files, refs, branches, commits or repository-local temporary directories.

A dirty or unsafe source worktree produces `BLOCKED_BY_GIT_STATE` and lists every detected condition.

## 8. Git capability contract

The check returns one primary result:

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

### 8.1 Base resolution

When `HEAD` is attached, the current branch is the base candidate.

For detached `HEAD`, PlanAnvil must establish one unambiguous appropriate local or remote containing branch. Otherwise it stops with `GIT_BASE_AMBIGUOUS`. It must not guess from branch names alone.

### 8.2 Reversible capability probe

Before writing planning artifacts, PlanAnvil MUST test:

1. temporary ref creation, verification and deletion;
2. planning branch creation from `BASE_SHA`;
3. linked worktree creation;
4. creation and removal of a probe file in the temporary worktree;
5. index update;
6. a probe commit unless signing or hooks make that unsafe;
7. worktree removal and branch deletion;
8. confirmation that the source branch, `HEAD`, index and files are unchanged.

Use unique names such as:

```text
refs/plananvil/probes/<RUN-ID>
plananvil/probe/<RUN-ID>
```

A ref-only probe is insufficient for `GIT_READY`.

For Git read-only or write-restricted results, PlanAnvil may only advise starting Codex with suitable Git metadata permissions or asking the user to create the planning branch and worktree manually. It must not elevate privileges or bypass the sandbox.

## 9. Planning branch and worktree

For `GIT_READY`, create:

```text
Planning branch: pursue/plan/<PLAN-ID>/<slug>
Planning worktree: external path selected by the implementation
```

The absolute planning worktree path is recorded in `manifest.json`. It must be outside the source worktree.

The planning branch may contain only:

- `.pursue/SYSTEM_PROFILE.md`;
- ignore rules for `.pursue/SYSTEM_PROFILE.local.md` and ephemeral files;
- PlanAnvil run artifacts;
- documentation directly required by the plan.

It must not contain product code or product tests.

The planning worktree remains available until execution finishes, the plan is rejected or it is explicitly archived. The final report warns against deleting it prematurely.

PlanAnvil commits planning artifacts, but does not push unless separately and explicitly requested and the profile confirms that pushing is safe.

## 10. Profiles

Profiles are created after the planning worktree exists and before goal analysis.

### 10.1 Repository profile

`.pursue/SYSTEM_PROFILE.md` is versioned and contains repository-safe information including:

- repository identity and structure;
- languages, runtimes and dependency managers;
- build, test, lint and static-analysis commands;
- architecture overview;
- Git conventions;
- quality gates;
- instruction map;
- general deployment, state and rollback rules;
- activation recommendation policy;
- risk thresholds;
- evidence and freshness metadata.

### 10.2 Local profile

`.pursue/SYSTEM_PROFILE.local.md` is ignored and contains machine-specific but non-secret information including:

- local paths and service names;
- process-manager, restart and health-check commands;
- deployment, switch and rollback procedures;
- permission requirements;
- CI or deployment triggers caused by pushes.

It must not contain passwords, tokens, credentials, private keys, certificates, cookies or copied `.env` content.

Because a later executor may start elsewhere, `manifest.json` stores the absolute local-profile path and hash. Resume fails when that file is missing or mismatched.

### 10.3 Evidence and freshness

Facts use `VERIFIED`, `USER_CONFIRMED`, `INFERRED` or `UNKNOWN`.

Profile validity uses `VALID`, `VALID_WITH_UNKNOWNS`, `PARTIALLY_STALE`, `STALE` or `UNVERIFIABLE`.

Important verified facts identify their evidence file or command. Freshness is based primarily on hashes of instruction, dependency, test, build, deployment, migration and PlanAnvil configuration files.

## 11. Project instructions

PlanAnvil MUST discover all applicable:

- `AGENTS.md`;
- `AGENTS.override.md`;
- configured fallback instruction filenames supported by Codex;
- nested instruction files within affected paths.

For each file record path, hash, byte size, full-read status, directory scope, precedence, affected stages, conflicts, truncation risk and safety-critical rules.

Automatically loaded content is not assumed complete. Full files must be read explicitly.

Documented scope and precedence resolve conflicts first. Remaining non-critical ambiguity uses the best-supported interpretation preserving project intent, safety, expected outcome, architecture and minimal change. The decision and evidence are recorded.

An inferred interpretation never overrides an explicit prohibition involving security, secrets, protected data, destructive operations, production, irreversible changes, branch protection, law or compliance.

A remaining safety-critical conflict produces `BLOCKED_BY_INSTRUCTION_CONFLICT`.

## 12. Run artifacts

Each run creates:

```text
.pursue/runs/<TIMESTAMP>_<PLAN-ID>_<SLUG>/
├── PLAN.md
├── manifest.json
├── state.json
├── compliance.json
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

Canonical machine state is JSON. Markdown reports may mirror it but must not override it.

All JSON artifacts conform to versioned schemas from `docs/ARTIFACT_SCHEMAS.md` and `.agents/skills/plan-anvil/schemas/`.

Updates to canonical state use write-to-temporary-file, flush, optional fsync, atomic replace and re-read validation. A half-written canonical state file is invalid.

## 13. Plan contract

`PLAN.md` contains stable decisions and guardrails. Stage-specific execution details belong in `stages/*.md`.

It must include:

- identity and contract version;
- a separate execution-run prompt;
- outcome and definition of done;
- generator stop boundary and executor stop conditions;
- scope and exclusions;
- assumptions, unknowns and evidence;
- applicable instructions and conflict resolutions;
- system and affected-component summary;
- data and state flow;
- dependencies and change classification;
- stable stage index;
- acceptance criteria;
- requirement-stage-risk-control-evidence traceability;
- Git, integration, production verification and rollback procedures;
- context, agent, resume and reconciliation rules;
- status model, next action and final-report requirements.

The plan must describe primarily what must be true. It must not contain speculative full implementations, unsupported signatures, stale permanent line numbers, unverified deployment commands or placeholders such as `TBD` and `TODO`.

## 14. Atomic stages and traceability

Each stage represents one logical independently testable result and has:

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
- one coherent commit;
- one verified checkpoint.

Split a stage when it spans independent domains, unrelated responsibilities, separate acceptance criteria, distinct risk profiles or independently deployable/rollbackable work.

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

## 15. Ambiguity and user decisions

For non-critical ambiguity, PlanAnvil makes the best supported interpretation, records its evidence and confidence and explains how it will be verified later.

The plan cannot become ready when missing information prevents safe definition of expected behavior, critical acceptance evidence, migration behavior, rollback, public API behavior, production switching, irreversible action or security/permission behavior. Use `BLOCKED_BY_CRITICAL_UNKNOWN`.

PlanAnvil asks the user only when a decision cannot be safely derived and changes:

- business outcome or feature scope;
- public behavior or API;
- architecture between viable choices with materially different consequences;
- data-loss or irreversible behavior;
- security, privacy, legal or permission policy;
- live-system switching;
- base-branch push or merge;
- a critical unknown blocking acceptance criteria or rollback.

Naming, file formats, script structure, validation order and non-critical ambiguity are technical decisions PlanAnvil should make and record.

## 16. Validation and blind review

Before `PLAN_READY`, deterministic validators check:

- required files and schema versions;
- no product-code or product-test changes;
- source-worktree immutability;
- planning-branch path allowlist;
- instruction completeness;
- stable identifiers;
- traceability completeness;
- risk-control coverage;
- absence of placeholders;
- consistency between JSON state and Markdown documents.

A fresh plan reviewer receives the goal, `PLAN.md`, stage briefs, profiles, instruction map, traceability data, risks and validator output, but not the planner's reasoning or self-review.

The reviewer writes a conclusion and hash before comparison. The blind artifact becomes immutable. Comparison may reference it but must never change it.

Readiness requires both deterministic validation and blind-review comparison to pass.

## 17. Hooks and planning agents

Hooks and custom planning-agent profiles are optional defense in depth, not the sole enforcement boundary.

When included, project configuration belongs under:

```text
.codex/config.toml
.codex/hooks.json
.codex/hooks/
.codex/agents/
```

The implementation must document trust/enablement and behavior when hooks are disabled or untrusted.

`SubagentStart` is audit and context injection only, never a hard blocker.

Every protected boundary also requires least-privilege sandboxing where available, explicit role instructions, deterministic allowed-path checks, post-agent filesystem/Git diff verification and checkpoint rejection on violations.

When hooks are unavailable, the run records `HOOKS_UNAVAILABLE` and may continue only because mandatory postcondition validation remains active.

## 18. Generated execution architecture

The generated plan defines:

```text
Jim
├── analysis agent
├── Jenny
├── implementation agent
├── independent verifier
└── Winston Wolfe, after exhausted strategies only
```

Jim manages sequencing, agents, files, checkpoints and gates but never changes production code or tests.

Jenny changes only approved test paths and test infrastructure and never production code.

Only one agent may modify repository files at a time.

The implementation retry model is:

```text
STRATEGY-A: ATTEMPT-A1, ATTEMPT-A2, ATTEMPT-A3
STRATEGY-B: ATTEMPT-B1, ATTEMPT-B2, ATTEMPT-B3
```

After three implementation failures, a materially different hypothesis and strategy are required. After six failures, Winston Wolfe performs read-only incident analysis and execution stops with `BLOCKED_BY_UNRESOLVED_FAILURE`.

Infrastructure failures consume an attempt only when caused by the implementation. Failed attempts remain auditable and are not hidden with stash, reset or clean.

## 19. Generated testing contract

Each behavior-changing stage uses:

```text
GREEN BASELINE
→ EXPECTED RED
→ IMPLEMENTATION
→ FULL GREEN
→ INDEPENDENT VERIFICATION
```

The red result must fail for the intended behavioral reason, not syntax, configuration, dependency, fixture or infrastructure failure.

Stages without testable software behavior define an equivalent evidence cycle rather than manufacturing a fake red test.

Every risk has a test, another control or an explicit reason no direct test applies.

## 20. Generated Git and live-verification contract

The later executor creates:

```text
Task branch: pursue/<PLAN-ID>/<slug>
Integration branch: pursue/integration/<PLAN-ID>/<slug>
```

Each completed stage ends in one coherent implementation-and-test commit.

The executor never pushes or merges to the base branch automatically.

Explicit user approval is required before changing the user's active local environment through an integration merge, switching a live worktree or service, executing an irreversible operation, or merging/pushing to the base branch.

Exact switch, restart, cache, deployment and rollback commands come from the revalidated local profile.

## 21. Resume and compaction

The future execution run is resumable from files and Git without previous conversation memory.

A checkpoint records stage, phase, result, branch, worktree, SHA, test evidence, Git status, risks, actual agent-tree audit, allowed-write audit, next action, recovery instructions and hashes of required artifacts.

Before compaction, a valid checkpoint must exist. `PreCompact` may delay compaction only until that checkpoint is durable.

After compaction:

```text
POST_COMPACT_EVENT
→ RECOVERY_POINTER
→ READ_MANIFEST_STATE_CHECKPOINT_PROFILES
→ RECONCILE_WITH_GIT
→ CONTINUE_OR_STOP
```

Conversation and hook context are never the source of truth.

## 22. Status model

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

## 23. Unsupported mechanisms

Undocumented or unavailable Codex mechanisms must not be simulated or claimed.

When a requirement cannot be implemented:

1. stop affected work;
2. verify current official documentation;
3. reproduce the behavior safely when possible;
4. record conflict and evidence;
5. preserve intent with a documented mechanism;
6. remove unsupported active behavior when no safe mechanism exists.

There is no `PARTIALLY_SUPPORTED` production behavior. A mechanism is active and validated, optional defense in depth, or absent.

## 24. Target repository layout

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
├── .codex/
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

## 25. Required tests

The implementation MUST have reproducible tests for:

- explicit activation and disabled implicit invocation;
- all clean and dirty preflight states;
- every Git capability result;
- detached-HEAD base resolution;
- source-worktree immutability;
- planning-worktree isolation;
- profile creation, freshness, ignore rules and secret rejection;
- instruction discovery, precedence, fallback names and truncation;
- small, large, stateful, irreversible and blocked plans;
- stable identifiers and traceability;
- JSON schemas and atomic state updates;
- blind immutable review;
- hook-enabled, hook-disabled and untrusted-hook modes;
- rejection of unauthorized paths and agent evidence;
- generated recovery and compaction contracts;
- platform behavior on Linux, macOS and Windows;
- observable stop after validation.

Capability tests retain exact commands/prompts, Codex version, model slug, OS, configuration, fixture commit, expected outcome, sanitized actual outcome and evaluation.

## 26. Completion criteria

PlanAnvil is complete only when:

1. it is discovered from `.agents/skills/plan-anvil`;
2. implicit invocation is disabled;
3. the generator/executor boundary is enforced;
4. lifecycle order matches section 6;
5. source preflight is read-only;
6. the complete Git probe succeeds or returns a precise blocker;
7. planning artifacts are isolated from the source worktree;
8. both profiles are created in the planning worktree;
9. the local profile is ignored and secret-safe;
10. all instructions are explicitly mapped and read fully;
11. canonical state passes versioned JSON schemas;
12. every run has a unique durable directory;
13. plans and stages use stable identifiers;
14. traceability has no critical gaps;
15. critical unknowns block readiness;
16. blind review remains immutable;
17. hooks remain optional defense in depth;
18. postcondition checks remain mandatory without hooks;
19. generated plans define the separate future execution topology;
20. generated plans contain testing, Git, integration, live verification, rollback, recovery and approval rules;
21. capability tests are reproducible;
22. `OPENAI_COMPLIANCE.md` has no unresolved active contradiction;
23. README accurately describes implementation status and use.

## 27. Implementation workflow

The implementing agent MUST:

1. read repository instructions and all normative docs;
2. verify a clean worktree and create a dedicated implementation branch;
3. re-check current official OpenAI documentation;
4. implement architecture and schemas before prompts;
5. implement the minimal native skill skeleton;
6. implement read-only preflight and the full Git probe;
7. implement planning-worktree creation;
8. implement profiles and instruction mapping;
9. implement schemas, templates and atomic state writes;
10. implement deterministic plan validation;
11. implement blind review and comparison;
12. add optional hooks and planning-agent profiles;
13. implement reproducible capability fixtures;
14. run available cross-platform quality gates;
15. review golden examples;
16. verify no secrets or machine-specific paths are committed;
17. verify the generator cannot modify product code or tests;
18. commit coherent units;
19. push only when explicitly authorized;
20. report exact evidence and remaining blockers.

## 28. Non-goals

PlanAnvil does not execute generated plans, implement product code or tests, automatically merge or push a base branch, elevate permissions, manage secrets, create staging infrastructure, guarantee reversal of irreversible actions, ignore explicit safety instructions, allow parallel repository modification, rely solely on hooks or conversational memory, integrate with Superpowers, or make the final business-acceptance decision.
