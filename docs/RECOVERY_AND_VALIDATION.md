# PlanAnvil — Recovery and Validation Guarantees

This document records the deterministic mechanisms used to satisfy the recovery, schema, path-safety and review requirements of contract 2.1.

## Atomic run scaffolding

A new run is built under an ignored sibling staging directory:

```text
.pursue/runs/.plananvil-scaffold-<RUN-ID>/
```

A sibling JSON journal records `PREPARED`, `BUILDING`, `READY_TO_PUBLISH` and `PUBLISHED`. The public run directory is created only by an atomic rename after all required files pass their versioned schemas. A retry may rebuild an unpublished staging directory or validate and reuse a complete published run. An incomplete public run is never silently overwritten.

## Crash-resumable immutable phases

Instruction mapping, goal analysis, review-bundle creation, blind-review recording and comparison use immutable, idempotent publication. A retry accepts only semantically equivalent content, ignoring explicitly volatile timestamp metadata. Rollback removes only files created by the current attempt.

Finalization first checks whether `HEAD` already contains a valid `STOPPED` state and final report. When it does, working-tree state is reconciled from the existing commit instead of creating a duplicate final commit.

## Checkpoints and compaction

`PreCompact` accepts a checkpoint only when all of the following remain valid:

- checkpoint schema and canonical JSON;
- state-recorded checkpoint hash;
- mode, stage, phase and next action;
- branch, linked worktree, HEAD and Git status;
- agent-tree and write-scope audits;
- referenced evidence and artifact hashes;
- recovery instructions.

Generation checkpoints are created with:

```text
python .agents/skills/plan-anvil/scripts/create_generation_checkpoint.py \
  --planning . \
  --run-root .pursue/runs/<RUN-ID>
```

## Hook run identity

Hooks bind an event to a run through the event worktree, ignored `local-state.json` source-worktree identity and, when necessary, explicit `PLANANVIL_RUN_ID`. Multiple matching runs are fail-closed. Hidden scaffold staging directories are never treated as active runs.

## Path safety

All user-selectable run roots and affected/write paths use the shared path-safety policy. It rejects:

- repository escapes and traversal;
- `.git` in any letter case;
- symlink escapes;
- tracked Gitlinks/submodules unless an explicit future contract permits them;
- unsafe or root-wide write globs.

## Versioned schema coverage

Every allowed committed JSON artifact has an assigned versioned schema. Deterministic validation rejects an unknown JSON artifact role, a missing schema file, schema-invalid content or non-canonical JSON. Validation reports and the blind-review bundle have dedicated schemas.

## Instruction and traceability sealing

Before sealing:

- every instruction entry is bound to one or more stable stage IDs through `affected_stages`;
- the repository profile instruction section is replaced with the resolved hashed map;
- every requirement criterion belongs to one of that requirement's stages;
- non-behavior stages may use an equivalent evidence cycle without expected-red, while behavior-changing stages still require it.

## CI and release evidence

The repository workflow compiles scripts and runs the unittest suite on Linux, macOS and Windows. CI success is necessary but does not replace the Codex capability evidence packages required by `docs/CODEX_CAPABILITY_BASELINE.md`.
