# Recovery delivery and evidence audit — 2026-09-05

## Scope and authority

Baseline input: PlanAnvil `57909a810b3ceb9deeac8550fd510dc4df28a951`; qualification [run #22](https://github.com/KeyffMS/PlanAnvil/actions/runs/33978465210). C13 was reproduced using its allowed project-scoped fallback and its runtime is unchanged. C09 timed out and C10 lacked exact echo in the isolated after-compaction probe. The previous audit's assumption that PostCompact was a model-context channel was incorrect.

The implementation specification gives current official Codex documentation priority. This is a product/output-contract correction, not a waiver of capability requirements. No offline test here is evidence that the live capability is reproduced.

## Source-verified recovery channel

The [official hooks reference](https://developers.openai.com/codex/hooks/) explicitly limits PostCompact output to common fields and ignores plain stdout. SessionStart matches `source`; `source=compact` runs before the immediate next model request, including compaction in the middle of a turn.

Pinned Codex source at `rust-v0.153.4`:

| File | Boundary |
|---|---|
| [hooks/src/events/compact.rs](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/hooks/src/events/compact.rs) | StatelessHookOutcome and parsing have no additional-context return channel. |
| [core/src/hook_runtime.rs](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/core/src/hook_runtime.rs) | run_post_compact_hooks emits events/control only; pending SessionStart uses record_additional_contexts. |
| [hooks/src/events/session_start.rs](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/hooks/src/events/session_start.rs) | SessionStart source matching and additionalContext interpretation. |
| [config/src/loader/mod.rs](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/config/src/loader/mod.rs) | Linked-worktree hook declarations come from the corresponding primary checkout. |

Product behavior: PostCompact reports checkpoint readiness through universal `systemMessage`, with `continue=true`, without including the next-action target. SessionStart supplies the existing pointer/context. This does not change canonical state, checkpoint validation, source ownership or the generator/executor separation.

C10 tests startup and after-compaction recovery in independent real product fixtures with different opaque targets. The second fixture narrows SessionStart to `^compact$` in the primary checkout BEFORE commit/bootstrap. It must observe PreCompact, PostCompact and subsequently SessionStart(source=compact), with no ordinary startup record. PostCompact output must contain no additional context. A matching product-emitted target, exact model echo, allowed tool usage, checkpoint validity and source/planning immutability are all required. The existing two acceptance assertion strings are unchanged.

## C09/C10 observation and timeout boundary

Only the C09/C10 process invocations opt into the new observed runner. It retains event counts, the last 128 structural events, exact allowlisted command labels, category-only error counts, and process exit/cleanup status. It never retains raw stdout/stderr, command output, unknown command text, prompts or thread IDs. Lines are size-bounded; malformed/oversized diagnostics are counted.

On timeout, terminate the owned process group on POSIX or process tree on Windows, wait for it and drain bounded reader threads before proceeding. A cleanup/reader failure blocks the probe. This prevents a CLI launcher timeout from silently leaving its ordinary descendants running during the next capability. It does not claim to control a process which deliberately escapes its owned group/tree.

C09 retains a bounded structural hook sequence as well. The 900-second timeout, compaction threshold, two-cycle/continuation/checkpoint requirements and rejection of incomplete results remain. We have not proved the cause of the remaining C09 timeout and do not claim to have fixed its runtime completion. C08's intentional negative-path handling and C13's runner are unchanged.

C10 compares the real product's emitted target against an outer-generated digest, then checks the structured model payload both before and after sanitization. Persisted value-flow diagnostics contain booleans/counts/lengths and fixed classification labels, not proof values or their hashes. Wrong-format echo is diagnosed but not accepted.

## Complete, limited evidence upload

The workflow builds a deterministic inner ZIP from validated staged evidence. Packaging requires exactly C01-C16 manifests plus top-level summary/index/guide. Each listed file, including the three hidden fixture files, is hash-checked; unlisted files and symlinks are rejected. ZIP verification independently checks per-capability manifests and the archive manifest, with path and size limits. Removing a hidden member and rewriting only the outer manifest still fails.

Only the verified archive is uploaded, not the runner workspace or an unrestricted set of dotfiles. Packaging failure also fails the selected gate. The downloaded Actions artifact contains this inner evidence ZIP. No secret-bearing runtime files are added to the allowlist.

## Regression strategy and handoff

Executable tests cover real product hook output at PostCompact and SessionStart(source=compact), the installer/Git/start/checkpoint path, root-source matcher isolation, exact echo acceptance, proof-safe diagnostic comparison, actual process timeout/descendant cleanup, partial event retention, malformed/oversized streams and strict archive verification. Existing product and qualification suites remain mandatory. The offline lifecycle driver only treats documented SessionStart output as model context; it does not pretend that arbitrary PostCompact JSON is injectable.

The existing hosted OS/Python matrix runs `test_qualification_*.py` in addition to core product tests. Qualification results remain BLOCKED until new live evidence is produced. Use the existing workflow on main with `mode=recovery`; that selects C09/C10/C13 through the same runtimes as full and cannot claim a C01-C16 release pass. Do not rerun full until the targeted results are understood.
