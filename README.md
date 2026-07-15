# PlanAnvil

PlanAnvil is a Codex-native repository skill that turns a software-engineering goal into a rigorous, test-driven, auditable implementation contract.

It **generates and validates a plan but never executes it**. Product implementation happens only in a separate later Codex run using the execution prompt written into `PLAN.md`.

## Status

The deterministic generator core, schemas, templates, tests, optional planning agents, and defense-in-depth hooks are implemented.

Release status is **candidate**, not production-ready. The Codex capability matrix in `docs/CODEX_CAPABILITY_BASELINE.md` remains a release gate until the required tests have committed sanitized `REPRODUCED` evidence for the current Codex version, model, operating systems, permission modes, and project-trust modes.

## Use

The repository skill is discovered from:

```text
.agents/skills/plan-anvil/
```

Implicit invocation is disabled. Invoke it explicitly:

```text
$plan-anvil Generate a plan to add validation that rejects an empty display name.
```

A run must:

1. verify a clean source worktree;
2. run a real reversible Git ref, branch, worktree, index, and commit probe;
3. create an isolated planning branch and external linked worktree;
4. preserve schema-validated Git/lifecycle bootstrap evidence;
5. profile the repository, map complete applicable instructions, and record immutable goal analysis;
6. author stable plan, stage, risk, control, and traceability artifacts;
7. pass deterministic validation and immutable blind review;
8. commit planning artifacts only;
9. report the result and stop without implementing anything.

The deterministic controller can also be inspected directly:

```text
python .agents/skills/plan-anvil/scripts/plan_anvil.py start \
  --source . \
  --goal "Add validation that rejects an empty display name."
```

The bootstrap controller stops after isolation, profiling, run scaffolding, and durable bootstrap evidence. The skill then performs evidence-based analysis and plan authoring before deterministic validation, blind review, and the planning-only commit gate.

## Safety boundary

PlanAnvil does not modify application code or tests, execute generated stages, deploy, migrate, restart services, switch a live environment, use destructive Git cleanup, or push or merge the base branch.

The retained planning worktree is the durable control root. Machine-specific paths remain only in ignored local files; committed artifacts use repository-relative paths and Git identity.

Project-scoped `.codex` agents and hooks are optional. Hooks require project trust and remain defense in depth; mandatory filesystem and Git postconditions apply in every hook mode.

## Requirements

- Python 3.11 or newer;
- Git 2.30 or newer;
- no elevated privileges;
- no third-party Python packages for the deterministic core;
- no network access for local validation.

## Validation

```text
python -m unittest discover -s .agents/skills/plan-anvil/tests -v
python -m compileall -q .agents/skills/plan-anvil .codex/hooks
```

## Documentation

- `docs/IMPLEMENTATION_SPEC.md` — authoritative product and implementation contract
- `docs/ARCHITECTURE.md` — architecture and trust boundaries
- `docs/ARTIFACT_SCHEMAS.md` — canonical state and artifact formats
- `docs/RECOVERY_AND_VALIDATION.md` — crash recovery, checkpoint, schema and path-safety guarantees
- `docs/OPENAI_COMPLIANCE.md` — Codex compatibility decisions
- `docs/CODEX_CAPABILITY_BASELINE.md` — reproducible capability release gate
- `docs/EXAMPLES.md` — expected decisions and output shapes
- `capabilities/README.md` — evidence-package workflow

## Author

[KeyffMS](https://github.com/KeyffMS) / [aiteracja.pl](https://aiteracja.pl)
