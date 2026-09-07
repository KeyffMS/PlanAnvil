# C10 configuration provenance

Use the v7 runner live-auth/persisted-trust context. Do not copy or restore authentication tokens; restore runner config.toml byte-for-byte after the probe.

The startup fixture retains the product SessionStart hook. The independent after-compaction fixture retains PreCompact and PostCompact and narrows SessionStart to ^compact$ at the primary hook source. Check that the linked checkout has identical declarations. Prepare this BEFORE product snapshots/checkpoints. Model context comes only from SessionStart(source=compact), whose handler output is checked before examining the model echo.

Sandbox remains read-only, approval never, and model-tool network disabled. Low auto-compaction threshold and token_budget=false apply only to disposable fixtures, not product defaults. Preserve the process's bounded structural progress on timeout and kill its owned process group/tree before continuing the harness.
