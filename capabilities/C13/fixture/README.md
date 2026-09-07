# C13 fixture

Both the ephemeral attempt and the recognized-error-only fallback use:
- project-scoped agent `.codex/agents/fixture_agent.toml`;
- explicit `[agents.fixture_agent]` with `config_file = "./agents/fixture_agent.toml"`;
- spawn request with `agent_type` exactly `fixture_agent`;
- project-scoped `SubagentStart` matcher `^fixture_agent$`;
- a proxy command with arguments `SubagentStart subagent-start-fixture.py`.

The fallback uses a separate disposable Git repository and an isolated CODEX_HOME. It does not materialize a home-scoped agent or hook. The sandbox remains read-only and repository state must remain unchanged. No manual invocation of the fixture hook can count as live evidence.
