# PlanAnvil

A Codex-native skill for generating rigorous, test-driven, auditable software implementation plans.

PlanAnvil **generates and validates a plan but never executes it**. Implementation happens only in a separate later Codex run using the execution contract written into `PLAN.md`.

## Current status

The repository currently contains the authoritative implementation contract and compatibility baseline. The production skill and its deterministic test suite are not yet implemented.

## Documentation

- [`docs/IMPLEMENTATION_SPEC.md`](docs/IMPLEMENTATION_SPEC.md) — authoritative product and implementation contract
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — generator architecture and trust boundaries
- [`docs/ARTIFACT_SCHEMAS.md`](docs/ARTIFACT_SCHEMAS.md) — canonical state and artifact formats
- [`docs/OPENAI_COMPLIANCE.md`](docs/OPENAI_COMPLIANCE.md) — current Codex compatibility decisions
- [`docs/CODEX_CAPABILITY_BASELINE.md`](docs/CODEX_CAPABILITY_BASELINE.md) — reproducible capability-test requirements
- [`docs/EXAMPLES.md`](docs/EXAMPLES.md) — expected decisions and output shapes

## Core guarantees

A production PlanAnvil run must:

- require explicit `$plan-anvil` activation;
- start from a clean Git worktree;
- verify actual Git branch, worktree, index, and commit capabilities;
- create an isolated planning branch and worktree;
- leave the source worktree unchanged;
- profile the repository and map all applicable project instructions;
- generate stable stages, acceptance criteria, risks, tests, and rollback procedures;
- perform deterministic validation and immutable blind plan review;
- commit only planning artifacts;
- stop without implementing product code or tests.

## Target installation

The canonical skill path is:

```text
.agents/skills/plan-anvil/
```

Implicit invocation is disabled.

Optional project-scoped Codex agents and hooks live under `.codex/`, but hooks remain defense in depth rather than the sole enforcement boundary.

## Author

[KeyffMS](https://github.com/KeyffMS) / [aiteracja.pl](https://aiteracja.pl)
