# PlanAnvil — Architecture

> This document explains how the implementation satisfies `IMPLEMENTATION_SPEC.md` version 2.1.  
> It is subordinate to the implementation specification and current official OpenAI documentation.

## 1. Architectural split

PlanAnvil has two strictly separated layers:

| Layer | Active during PlanAnvil run | Modifies product code | Responsibility |
|---|---:|---:|---|
| Generator runtime | Yes | No | Inspect, profile, generate, validate and commit the plan |
| Generated execution contract | Document only | Later, in a separate run | Control implementation, testing, integration and recovery |

The generator never starts Jim, Jenny, an implementation agent or Winston Wolfe. These are definitions written into the generated plan.

The generator may use its own read-only profiler and reviewer agents. Their identities, permissions and outputs are separate from future execution roles.

## 2. Components

```text
$plan-anvil
    |
    v
Skill controller
    |
    +--> Read-only source preflight
    +--> Git capability probe
    +--> Planning worktree manager
    +--> Repository profiler
    +--> Instruction mapper
    +--> Goal analyzer
    +--> Artifact generator
    +--> Deterministic validator
    +--> Blind plan reviewer
    +--> Comparison validator
    +--> Planning commit writer
    `--> Final reporter and hard stop
```

The controller is the only component allowed to advance canonical state.

Core deterministic scripts use Python 3.11+ and the standard library. Each command:

- accepts explicit paths and identifiers;
- emits structured JSON to stdout;
- writes diagnostics to stderr;
- uses stable exit codes;
- never treats conversation text as canonical state;
- is safe to rerun unless explicitly documented otherwise.

Canonical entry points include:

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

## 3. State machine

```text
NEW
→ SOURCE_PREFLIGHT_PASSED
→ GIT_READY
→ PLANNING_WORKTREE_READY
→ PROFILE_READY
→ INSTRUCTION_MAP_READY
→ ANALYSIS_READY
→ ARTIFACTS_GENERATED
→ DETERMINISTICALLY_VALID
→ BLIND_REVIEW_WRITTEN
→ COMPARISON_VALID
→ PLAN_COMMITTED
→ STOPPED
```

No state may be skipped.

A transition is valid only when:

- required input hashes match;
- the previous state's postconditions pass;
- `state.json` is atomically updated;
- the new state identifies exactly one next action.

Failures use explicit blocking or failure states and preserve evidence.

## 4. Filesystem and branch ownership

### 4.1 Source worktree

The source worktree is read-only for the generator.

Allowed operations are file reads, Git reads, configuration reads and demonstrably non-mutating diagnostics.

File writes, index changes, branch switching, commits, cleanup and profile creation are forbidden.

### 4.2 Planning worktree and control root

The planning worktree is the only repository worktree writable by the generator.

Allowed committed locations are:

```text
.pursue/SYSTEM_PROFILE.md
.pursue/runs/<RUN-ID>/
.gitignore or equivalent ignore rules required by PlanAnvil
plan-specific documentation explicitly required by the contract
```

The planning worktree remains the durable control root during later execution.

The later executor:

- reads `PLAN.md` and stage briefs from the control root;
- writes state, checkpoints, reports and evidence to the control root;
- may commit those control artifacts to the planning branch;
- modifies product code and tests only in task or integration worktrees.

`PLAN.md`, stage briefs and approved acceptance criteria are immutable during execution unless the generated change protocol creates a versioned replacement and repeats validation.

### 4.3 Ignored local state

Machine-specific paths are stored only in ignored local files:

```text
.pursue/SYSTEM_PROFILE.local.md
.pursue/runs/<RUN-ID>/local-state.json
```

`local-state.json` contains absolute source, planning and local-profile paths and local hashes.

It is never committed or pushed.

Committed `manifest.json` contains repository identity, branches, SHAs and repository-relative paths only.

The final terminal report may display absolute paths transiently.

### 4.4 External temporary directory

Git probes use an external temporary parent directory outside every repository worktree.

Temporary resources:

- include the run ID;
- are removed after successful verification;
- are reported precisely when cleanup fails;
- block real plan generation when cleanup cannot be verified.

## 5. Data model

Human-readable contracts:

- `PLAN.md`;
- `stages/STAGE-*.md`;
- narrative reports.

Committed canonical state:

- `manifest.json`;
- `state.json`;
- `compliance.json`;
- `traceability.json`;
- risk files;
- checkpoint and report sidecars.

Ignored local state:

- `local-state.json`;
- `SYSTEM_PROFILE.local.md`.

Canonical JSON uses UTF-8, LF line endings, sorted keys, two-space indentation, a terminal newline, RFC 3339 UTC timestamps and SHA-256 hashes.

## 6. Atomic writes and locks

Mutable canonical state is updated using:

```text
read and validate current revision
→ build complete replacement
→ write sibling temporary file
→ flush and fsync where supported
→ atomic replace
→ fsync containing directory where supported
→ reread and validate
```

`state.json` contains a monotonic revision.

Generation and execution locks use exclusive-create semantics and record run ID, host, process or session identity, creation time, heartbeat and owner command.

A lock is stale only when its timeout elapsed and owner liveness or session evidence confirms inactivity.

A non-stale lock is never removed automatically.

## 7. Git architecture

### 7.1 Probe versus real planning worktree

The probe creates disposable refs, a branch and a linked worktree. It verifies every Git operation required by the real generator, including an actual commit under current identity, signing and hook policy.

`GIT_READY` is impossible when the commit check is skipped or fails.

The real planning worktree is created only after probe cleanup and source-state revalidation succeed.

### 7.2 Commit policy

Before a planning or control commit:

- validate allowed paths;
- validate no product code or tests exist in the control branch diff;
- validate source worktree identity and cleanliness;
- validate branch and base identity;
- validate canonical schemas;
- validate local files are ignored and absent from the index;
- validate blind review and comparison where required.

Commit signing follows repository policy. PlanAnvil never disables signing or hooks silently.

### 7.3 Push policy

Push is outside the default PlanAnvil run.

A separate explicit request is required and the profile must confirm that pushing the planning branch will not trigger unsafe deployment or external actions.

## 8. Instruction architecture

Instruction discovery combines:

1. documented Codex discovery and precedence;
2. explicit scanning for every affected path scope.

The explicit instruction map is authoritative for validation.

Each planning agent receives exact instruction paths, expected hashes, the full-read requirement and affected scope.

If an instruction changes after mapping, dependent analysis is stale.

## 9. Blind review

The controller builds a review bundle containing only:

- original user goal;
- evidence index;
- profiles;
- instruction map;
- generated plan and stages;
- traceability and risks;
- deterministic validation output.

The reviewer does not receive planner reasoning or self-review.

The reviewer writes:

```text
reports/plan-review/blind-review.md
reports/plan-review/blind-review.json
```

Both files are hashed before the comparison phase. Comparison writes new artifacts and never edits the blind review.

## 10. Optional planning agents

Optional project-scoped agents live under `.codex/agents/`.

`plan-anvil-profiler` is read-only and gathers repository evidence.

`plan-anvil-reviewer` receives fresh context and writes one immutable blind report.

Custom agent configuration is convenience and reproducibility support, not the sole permission boundary.

The core generator must remain functional without custom agents by dispatching equivalent fresh read-only roles through supported runtime mechanisms.

## 11. Optional hooks and trust modes

Optional project hooks live in `.codex/hooks.json`, inline `.codex/config.toml`, or `.codex/hooks/` scripts.

The runtime records one hook mode:

```text
HOOKS_TRUSTED
HOOKS_DISABLED
HOOKS_UNTRUSTED
HOOKS_UNAVAILABLE
```

Only `HOOKS_TRUSTED` permits a report to claim hook enforcement.

Hooks may warn, deny supported destructive commands or paths, record agent relationships and delay compaction until a durable checkpoint exists.

Hooks never replace deterministic postconditions.

For JSON definitions, use `commandWindows` for a Windows override. TOML may use `command_windows` or `commandWindows` as supported by current official documentation.

Commands run from the session working directory, so repository-local hooks resolve scripts from the Git root.

## 12. Cross-platform contract

Canonical scripts use `pathlib`, `os`, `tempfile`, `json`, `hashlib`, `subprocess` argument arrays and other standard-library facilities.

They avoid shell execution unless shell semantics are the subject of a controlled test.

Path validation:

- rejects traversal and symlink escapes;
- handles case-insensitive filesystems;
- normalizes repository-relative matching to POSIX separators;
- rejects `.git` writes except through dedicated Git commands;
- treats submodules as separate boundaries unless explicitly in scope.

## 13. Security boundaries

No single mechanism is a complete security boundary.

Controls combine:

- Codex sandbox and approval mode;
- project instructions;
- optional custom roles;
- optional trusted hooks;
- path allowlists;
- Git and filesystem snapshots;
- deterministic postconditions;
- immutable evidence;
- checkpoint rejection.

Secrets and local paths are excluded through profile rules, schema separation, ignored local files, filename rules, content checks and final diff validation.

## 14. Failure handling

A failure records:

- explicit status;
- failed state and phase;
- preserved evidence;
- safe remediation;
- any temporary resources left behind.

PlanAnvil never hides a failure with stash, reset, clean or destructive cleanup.

## 15. Packaging

The v1 core package is:

```text
.agents/skills/plan-anvil/
```

Optional defense-in-depth integration may additionally provide:

```text
.codex/agents/plan-anvil-*.toml
.codex/hooks.json
.codex/hooks/plan-anvil-*.py
```

An optional installer:

- shows every destination;
- refuses conflicting overwrites without explicit approval;
- merges configuration deterministically or stops;
- never enables project trust automatically.

Plugin packaging is a later distribution option and must preserve the same product boundary.
