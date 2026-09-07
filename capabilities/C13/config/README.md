# C13 sandbox configuration — baseline 2.3

Use the deterministic v7 live qualification harness rather than an interactive manual session.

```toml
[agents]
enabled = true
max_concurrent_threads_per_session = 2

[agents.fixture_agent]
description = "C13 qualification child for real SubagentStart context semantics."
config_file = "./agents/fixture_agent.toml"
```

- model: `gpt-5.6-sol`;
- approval: `never`;
- sandbox: `read-only`;
- model-tool network: disabled;
- project trust persisted in the disposable user config, never passed as a projects CLI override;
- real project-scoped agent and `SubagentStart` hook;
- filename/name/matcher: `fixture_agent.toml` / `fixture_agent` / `^fixture_agent$`;
- real spawn request uses `agent_type=fixture_agent`.

Transport is ephemeral-first. A non-ephemeral retry is allowed only for the recognized parent-thread registration failure. The retry uses a disposable CODEX_HOME, temporary file-backed auth symlink, isolated SQLite/log paths, history.persistence="none", mandatory cleanup, and auth-metadata verification. No home-scoped synthetic agent or hook substitutes for the project integration.
