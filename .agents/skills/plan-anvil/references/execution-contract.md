# Separate execution-run contract

These rules are written into the generated plan; they are never started by PlanAnvil.

## Roles and topology

The later executor uses a flat direct-child topology: Jim coordinates, Jenny owns approved tests only, one implementation agent modifies approved product paths, an independent verifier remains read-only, and Winston Wolfe performs read-only incident analysis only after six exhausted implementation attempts.

Jim never modifies product code or tests. Jenny never modifies production code. Only one agent modifies repository files at a time.

Configured child roles must be spawned with their exact `agent_type`; do not substitute an unnamed/default child when a role-specific hook or instruction boundary is required. In Codex 0.152, `SubagentStart` matchers receive `agent_type` as matcher input.

## Tool and mutation boundary

Treat `PreToolUse` as an early guard, not the sole enforcement boundary. Codex 0.152 can surface file changes through transports for which a project hook is not a reliable complete mutation ledger. Every implementation/test mutation therefore requires an immediate deterministic postcondition before the next modifying action:

1. enumerate the actual changed paths from Git and the filesystem;
2. prove every path is inside the approved task/test scope for the active stage;
3. prove the control/planning worktree and source/base worktree remain outside the mutation set;
4. stop and restore from the stage recovery point if the mutation escaped scope.

Prefer the runtime's native freeform `apply_patch` path when available, but never infer safety from a successful `apply_patch`, `file_change` item, or missing hook event. Shell, patch, edit, write, and write-capable MCP paths are subject to the same postcondition.

## Evidence cycle

Behavior-changing stages use:

`GREEN BASELINE → EXPECTED RED → IMPLEMENTATION → FULL GREEN → INDEPENDENT VERIFICATION`

The red result must fail for the intended behavioral reason. Non-behavior stages use an equivalent evidence cycle.

## Retry model

Use STRATEGY-A with ATTEMPT-A1, ATTEMPT-A2, and ATTEMPT-A3, then STRATEGY-B with ATTEMPT-B1, ATTEMPT-B2, and ATTEMPT-B3. Preserve failed-attempt evidence. After six implementation failures, run read-only incident analysis and stop with `BLOCKED_BY_UNRESOLVED_FAILURE`.

## Git and control ownership

Task branch: `pursue/<PLAN-ID>/<slug>`. Integration branch: `pursue/integration/<PLAN-ID>/<slug>`.

Control state, reports, checkpoints, and evidence stay in the retained planning worktree. Product code and tests change only in task or integration worktrees. Each completed stage ends in one coherent implementation-and-test commit.

Never automatically push or merge the base branch. Require explicit user approval before a base merge or push, live switching, irreversible operations, or base integration.

## Compaction and recovery

`PreCompact`/`PostCompact` are lifecycle events, not exact-token timers. In Codex 0.152 the configured auto-compaction limit can be increased by a token-budget fallback buffer. Recovery correctness must depend on observed lifecycle events and canonical checkpoint/Git state, never on an assumed raw token count.

## Stateful changes

Use discover, recovery point, expand, migrate, switch, observe, and a separate later contraction. Require resumability, integrity checks, compatibility, rollback evidence, and explicit approval for irreversible steps.
