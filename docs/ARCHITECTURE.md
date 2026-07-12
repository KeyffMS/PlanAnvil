# PlanAnvil — Architecture

> This document explains how the implementation satisfies `IMPLEMENTATION_SPEC.md`.  
> It is subordinate to the implementation specification and current official OpenAI documentation.

## 1. Architectural split

PlanAnvil has two strictly separated products in one output flow:

| Layer | Exists during PlanAnvil run | Modifies product code | Responsibility |
|---|---:|---:|---|
| Generator runtime | Yes | No | Inspect, profile, plan, validate, commit planning artifacts |
| Generated execution contract | Document only | Later, in a separate run | Describe controlled implementation, testing, integration, and recovery |

The generator never instantiates Jim, Jenny, an implementation agent, or Winston Wolfe. Those are role definitions written into the generated plan.

The generator may use its own read-only profiler and reviewer agents. Their names and permissions are distinct from future execution roles.

## 2. Components

```text
$plan-anvil
    |
    v
Skill controller
    |
    +--> Read-only source preflight
    |
    +--> Git capability probe
    |
    +--> Planning worktree manager
    |
    +--> Repository profiler
    |
    +--> Instruction mapper
    |
    +--> Goal analyzer
    |
    +--> Artifact generator
    |
    +--> Deterministic validator
    |
    +--> Blind plan reviewer
    |
    +--> Comparison validator
    |
    +--> Planning commit writer
    |
    `--> Final reporter and hard stop
```

### 2.1 Skill controller

The controller implements the state machine and is the only component allowed to advance the run state.

It must not contain business-specific planning knowledge that belongs in references or templates.

### 2.2 Deterministic scripts

Canonical scripts are Python 3.11+ and standard-library-only.

Each command:

- accepts explicit paths and identifiers;
- emits structured JSON to stdout;
- writes diagnostics to stderr;
- uses stable exit codes;
- never parses conversational text as authoritative state;
- is safe to rerun unless documented otherwise.

Suggested commands:

```text
preflight.py
test_git_capabilities.py
create_planning_worktree.py
profile_repository.py
validate_profile.py
map_instructions.py
scaffold_run.py
validate_artifacts.py
validate_plan.py
validate_diff.py
commit_plan.py
```

### 2.3 Planning agents

Project-scoped agents live under `.codex/agents/`.

`plan-anvil-profiler`:

- read-only;
- gathers repository evidence;
- does not make final product decisions;
- writes only through the controller's approved report path when write access is required.

`plan-anvil-reviewer`:

- fresh context;
- read-only;
- receives plan evidence but not planner reasoning;
- produces one immutable blind report.

Custom agent configuration is convenience and reproducibility support, not the sole permission boundary.

### 2.4 Hooks

Project hooks live in `.codex/hooks.json` and `.codex/hooks/*.py`.

Hooks may:

- warn about unexpected tool paths;
- deny supported destructive Git commands;
- deny supported writes outside approved planning paths;
- record subagent identifiers and parent relationships;
- delay compaction until a durable checkpoint exists.

Hooks cannot replace deterministic postconditions.

The controller must operate correctly when hooks are disabled or untrusted, while recording that hook enforcement was unavailable.

## 3. State machine

```text
NEW
 |
 v
SOURCE_PREFLIGHT
 | failure -> BLOCKED_BY_GIT_STATE
 v
GIT_CAPABILITY_CHECK
 | failure -> BLOCKED_BY_GIT_PERMISSIONS or runtime-specific blocker
 v
PLANNING_WORKTREE_READY
 v
PROFILE_READY
 v
INSTRUCTION_MAP_READY
 v
ANALYSIS_READY
 v
ARTIFACTS_GENERATED
 v
DETERMINISTICALLY_VALID
 v
BLIND_REVIEW_WRITTEN
 v
COMPARISON_VALID
 v
PLAN_COMMITTED
 v
STOPPED
```

No state may be skipped.

A state transition is valid only when:

- required input hashes match;
- previous state postconditions pass;
- canonical `state.json` is atomically updated;
- the new state names exactly one next action.

## 4. Filesystem ownership

### 4.1 Source worktree

The source worktree is read-only for the generator.

Allowed operations:

- file reads;
- Git status and history reads;
- repository configuration reads;
- non-mutating command discovery.

Forbidden operations:

- file writes;
- index changes;
- branch switching;
- commits;
- cleanup;
- profile creation.

### 4.2 Planning worktree

The planning worktree is the only repository worktree writable by the generator.

Allowed paths are restricted to:

```text
.pursue/
.gitignore or equivalent ignore file, only for PlanAnvil local artifacts
documentation files explicitly required for the generated plan
```

The allowed-path validator compares both filesystem snapshots and Git diffs.

### 4.3 External temporary directory

Git probes may use an external temporary parent directory.

Temporary paths must:

- be outside every repository worktree;
- include the run ID;
- be removed on success;
- be preserved with a pointer when cleanup fails.

## 5. Durable planning root

The planning worktree is retained after PlanAnvil stops.

It contains:

```text
.pursue/SYSTEM_PROFILE.md
.pursue/SYSTEM_PROFILE.local.md
.pursue/runs/<RUN-ID>/
```

The final output contains:

- absolute planning-worktree path;
- relative and absolute plan paths;
- planning branch;
- planning commit;
- base branch and SHA.

A later execution run reads the plan from this durable planning root and creates implementation worktrees from `BASE_SHA`. It does not implement on the planning branch.

## 6. Data model

Human contracts:

- `PLAN.md`;
- `stages/STAGE-*.md`;
- narrative reports.

Canonical machine state:

- `manifest.json`;
- `state.json`;
- `compliance.json`;
- `traceability.json`;
- risk and checkpoint JSON files.

JSON schema version is independent from plan contract version.

All canonical JSON uses:

- UTF-8;
- LF line endings;
- sorted keys when written by deterministic scripts;
- two-space indentation;
- terminal newline;
- RFC 3339 UTC timestamps;
- SHA-256 hashes.

## 7. Atomic writes and concurrency

A canonical file update uses:

```text
read current state
→ validate expected revision
→ write sibling temporary file
→ flush and fsync file
→ atomic replace
→ fsync containing directory where supported
→ reread and validate
```

`state.json` contains a monotonic `revision`.

An execution lock is an atomic directory or exclusive-create file with:

- run ID;
- process ID where available;
- hostname;
- session ID where available;
- creation time;
- last heartbeat;
- owner command.

A lock may be considered stale only after both:

- its configured timeout elapsed;
- the owner process or session cannot be confirmed active.

PlanAnvil never deletes a non-stale lock automatically.

## 8. Git architecture

### 8.1 Probe versus real worktree

The probe creates disposable Git metadata and a disposable linked worktree. It proves the actual operations required later, including commit viability.

The real planning worktree is created only after the probe is fully cleaned and the source repository is revalidated.

### 8.2 Commit policy

Planning commits include only allowed artifacts.

Before commit:

- validate allowed paths;
- validate no product paths changed;
- validate source worktree identity and status;
- validate planning worktree branch and base;
- validate all canonical schemas;
- run blind review and comparison.

Commit signing follows repository policy. If signing is required and unavailable, PlanAnvil stops rather than disabling signing silently.

### 8.3 Push policy

Push is outside the default run.

A separate explicit user request is required, and the profile must confirm that pushing a planning branch does not trigger an unsafe deployment or external action.

## 9. Instruction architecture

Instruction discovery has two sources:

1. Codex documented discovery and precedence;
2. explicit filesystem scanning for every affected stage scope.

The explicit map is authoritative for PlanAnvil validation.

Each fresh planning agent receives:

- exact instruction paths;
- expected hashes;
- full-read requirement;
- affected path scope.

If a file changes after mapping, dependent analysis is stale.

## 10. Blind review architecture

The controller prepares a review bundle containing only:

- original user goal;
- evidence index;
- profiles;
- instruction map;
- generated plan;
- stage briefs;
- traceability;
- risks;
- deterministic validation output.

The reviewer writes:

```text
reports/plan-review/blind-review.md
reports/plan-review/blind-review.json
```

The controller hashes both files before exposing planner self-review.

Comparison writes a new artifact. It never edits the blind review.

## 11. Hook and trust modes

The runtime records one hook mode:

```text
HOOKS_TRUSTED
HOOKS_DISABLED
HOOKS_UNTRUSTED
HOOKS_UNAVAILABLE
```

Only `HOOKS_TRUSTED` permits a report to claim hook enforcement.

All modes still require postcondition validation.

Project `.codex/` configuration may be ignored in an untrusted project. The implementation must detect this rather than assuming agent or hook configuration loaded.

## 12. Cross-platform command contract

Each hook entry defines:

- `command` for POSIX systems;
- `commandWindows` or `command_windows` for Windows;
- explicit timeout;
- no dependence on the launch directory beyond the documented session `cwd`;
- repository-root resolution through Git rather than fragile relative paths.

Python scripts use `pathlib`, `subprocess` argument arrays, and no shell unless shell semantics are the subject of a controlled test.

## 13. Security boundaries

No single mechanism is a security boundary.

Controls combine:

- Codex sandbox and approval mode;
- project instructions;
- custom role configuration;
- hooks where trusted;
- write-path allowlists;
- Git and filesystem snapshots;
- deterministic postconditions;
- immutable evidence;
- checkpoint rejection.

Secrets are excluded by content scanning, filename rules, profile prompts, and final diff review.

## 14. Failure handling

A failure produces:

- explicit status;
- failed state and phase;
- preserved evidence;
- safe remediation;
- no destructive cleanup.

If a disposable probe cannot be cleaned, PlanAnvil reports exact refs, branches, and worktrees left behind. It does not continue to real plan generation.

## 15. Packaging

v1 is implemented as a repository skill plus project-scoped `.codex` integration.

An optional installer may copy:

```text
.agents/skills/plan-anvil/
.codex/agents/plan-anvil-*.toml
.codex/hooks.json
.codex/hooks/plan-anvil-*.py
```

The installer must:

- show every destination;
- refuse to overwrite conflicting files without explicit approval;
- merge configuration deterministically or stop;
- not enable trust automatically.

Plugin packaging is a later distribution option and must preserve the same product boundary.
