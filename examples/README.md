# Golden contract examples

These sanitized fixtures exercise the expected PlanAnvil decisions and output shapes. They contain planning contracts and evidence only; no product implementation is included.

- `small-change` — one low-risk behavior stage and `PLAN_READY`.
- `stateful-change` — five backward-compatible migration stages and `PLAN_READY`.
- `blocked-plan` — a destructive request stopped by critical policy unknowns.
- `git-write-restricted` — Git metadata restriction stops the run before profiles or plans are written.

The ready examples use schema version `1.1.0`, repository-relative paths, immutable review sidecars, comparison results, and sanitization reports. Live Codex capability evidence belongs under `capabilities/`, not here.
