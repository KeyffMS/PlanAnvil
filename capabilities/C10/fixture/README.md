# C10 independent recovery fixtures

Prepare each fixture through the actual installer, product start command, checkpoint creator and checkpoint validator. The model must not construct its own prerequisites.

Startup and after-compaction probes use independent source repositories, planning worktrees and opaque next-action targets. Narrow SessionStart to ^compact$ in the second root checkout BEFORE the fixture commit and bootstrap. Do not remove this supported recovery channel. Codex 0.153.4 redirects linked-worktree hook declarations to the root checkout; changing only planning/.codex/hooks.json is not isolation.

Require PreCompact -> PostCompact -> SessionStart(source=compact), no ordinary startup record, a matching target actually emitted by the product, and an exact model echo without unauthorized file/tool reads. PostCompact emits a universal readiness advisory and no next-action target.

Keep source and planning state unchanged. Persist only boolean/hash-comparison results and bounded structural observations, never the opaque values. Offline drivers model only documented SessionStart context delivery; they do not constitute live capability evidence.
