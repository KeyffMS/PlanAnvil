# PlanAnvil repository instructions

## Authority

Read `docs/IMPLEMENTATION_SPEC.md` first. Resolve conflicts in this order: current official OpenAI Codex documentation, the implementation specification, architecture, artifact schemas, compliance record, capability baseline, examples, then README.

## Product boundary

PlanAnvil generates, validates, and commits planning artifacts. It never implements or executes the generated plan. Preserve source-worktree immutability and the generator/executor separation in every change.

## Implementation rules

- Keep `.agents/skills/plan-anvil/SKILL.md` concise; put detail in references, schemas, templates, and deterministic scripts.
- Core scripts require Python 3.11+ and the standard library only.
- Use argument arrays rather than shell execution inside core scripts.
- Keep canonical JSON deterministic, schema-validated, atomically written, and free of local absolute paths or secrets.
- Treat `.pursue/SYSTEM_PROFILE.local.md` and every `local-state.json` as ignored local state.
- Optional `.codex` agents and hooks are defense in depth. Never claim that hooks are a complete enforcement boundary.
- Do not weaken Git signing, repository hooks, sandboxing, approvals, path allowlists, or postcondition checks.
- Do not mark runtime capability tests as reproduced without a committed sanitized evidence package.

## Validation

Run from the repository root:

```text
python -m unittest discover -s .agents/skills/plan-anvil/tests -v
python -m compileall -q .agents/skills/plan-anvil .codex/hooks
```

When changing schemas, lifecycle states, skill metadata, hooks, or agent configuration, also update the corresponding tests and compatibility documentation.
