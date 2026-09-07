# C12 sandbox configuration

Use a disposable project-scoped Codex configuration. Record the exact effective configuration in the sanitized result. Do not copy user/global secrets or unrelated settings.

PlanAnvil baseline settings when applicable:

```toml
[agents]
enabled = true
max_concurrent_threads_per_session = 4
```

For this fixture set a deliberately small documented `project_doc_max_bytes` value (for example 1024) so the oversized `fixture/AGENTS.md` exceeds the automatic instruction budget.
