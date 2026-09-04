# Codex 0.152 qualification trust contract

Live PlanAnvil qualification must model Codex CLI 0.152 project trust using the supported user-config path.

For C06, C08, C09, and C13 qualification probes:

- use a disposable, isolated `CODEX_HOME`;
- bridge authentication read-only through the existing qualification helper;
- persist `[projects."<absolute-project-path>"] trust_level = "trusted"` in that isolated home's `config.toml`;
- do not pass `projects.<path>.trust_level` through `-c/--config`;
- do not use `--ignore-user-config`, because that would discard the persisted trust decision;
- clean the isolated home after the probe and verify authentication metadata was unchanged.

This is qualification infrastructure, not a product configuration requirement. The PlanAnvil repository must not persist machine-specific trust paths.

C13 remains ephemeral-first. A recognized Codex 0.152 parent-thread registration failure (`collab spawn failed: no thread with id`) is a transport blocker even if `SubagentStart` fired before the failure. Only that recognized blocker permits the controlled non-ephemeral isolated-home fallback.
