# Separate execution-run contract

These rules are written into the generated plan; they are never started by PlanAnvil.

## Roles and topology

The later executor uses a flat direct-child topology: Jim coordinates, Jenny owns approved tests only, one implementation agent modifies approved product paths, an independent verifier remains read-only, and Winston Wolfe performs read-only incident analysis only after six exhausted implementation attempts.

Jim never modifies product code or tests. Jenny never modifies production code. Only one agent modifies repository files at a time.

## Evidence cycle

Behavior-changing stages use:

`GREEN BASELINE → EXPECTED RED → IMPLEMENTATION → FULL GREEN → INDEPENDENT VERIFICATION`

The red result must fail for the intended behavioral reason. Non-behavior stages use an equivalent evidence cycle.

## Retry model

Use three attempts for one strategy, then three attempts for a materially different strategy. Preserve failed-attempt evidence. After six failures, run read-only incident analysis and stop with `BLOCKED_BY_UNRESOLVED_FAILURE`.

## Git and control ownership

Task branch: `pursue/<PLAN-ID>/<slug>`. Integration branch: `pursue/integration/<PLAN-ID>/<slug>`.

Control state, reports, checkpoints, and evidence stay in the retained planning worktree. Product code and tests change only in task or integration worktrees. Each completed stage ends in one coherent implementation-and-test commit.

Never automatically push or merge the base branch. Require explicit approval before live switching, irreversible operations, or base integration.

## Stateful changes

Use discover, recovery point, expand, migrate, switch, observe, and a separate later contraction. Require resumability, integrity checks, compatibility, rollback evidence, and explicit approval for irreversible steps.
