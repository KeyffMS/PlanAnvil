# C09 finite recovery audit — 2026-09-06

## Scope and evidence boundary

Reviewed baseline: PlanAnvil `44f95258079d6b3ab5b79c178815bbc085edbe02`, live qualification #23 (`34021584365`), Codex CLI `0.153.4`. C10 and C13 passed in that run and their runtimes are not changed here. No live result is manufactured by offline testing.

#23 observed 20 successful commands and 20 automatic compaction cycles before the 900-second deadline; no PreCompact stop and no completed turn. Its content-free command labels were `other`. They do not establish which commands ran or prove the complete historical causal chain.

## Proven fixture defects

The active call path is v7.run_c09 -> compat._codex0152_compaction -> regression._patched_v4 -> v4._c09_runtime. The adapter overwrote C09's nominal threshold with **200 tokens** and replaced the generic prompt with eight repeated large reads. Bootstrap/checkpoint state still advertised **MAP_INSTRUCTIONS**, whereas the turn requested a separate compaction exercise. There was no checked finite phase protocol reconciling the canonical recovery instruction with the requested workload.

These are inspectable setup conflicts, not proof of a Codex deadlock. Raising the timeout or accepting partial event counts would not fix them. A very small trigger can repeatedly interrupt ordinary recovery tools; repeated payload reads without a stable explicit completion protocol also make progress fragile.

## Pinned upstream source review

All source references below are to `openai/codex`, tag `rust-v0.153.4`:

- `codex-rs/core/src/session/turn.rs`: mid-turn rollover requires `needs_follow_up` and either a new-window request or exhausted token budget. After successful automatic compaction the turn runs pending SessionStart hooks and continues sampling. A final response without follow-up can end the turn rather than forcing another rollover.
- `codex-rs/core/src/session/context_window.rs`: body-after-prefix usage is active tokens minus the window prefill baseline; the trigger includes an optional TokenBudget fallback buffer. The model hard context cap remains independent.
- `codex-rs/core/src/compact.rs`: compaction replaces history; mid-turn initial context is injected before the last user message. Actual PreCompact/PostCompact events bracket successful compaction. It does not make an arbitrary sequence of repeated tool calls finite.
- `codex-rs/core/src/hook_runtime.rs`: model-visible recovery after compaction uses pending SessionStart(source=compact). PostCompact is not an additional-context delivery channel.
- `codex-rs/core/src/tools/handlers/unified_exec.rs` and `unified_exec/exec_command.rs`: real exec_command accepts `cmd` and `max_output_tokens`; the original command is used for the canonical Bash hook and shell argv is used for execution.
- `codex-rs/core/tests/suite/compact.rs`: upstream integration tests drive real tool calls/compaction with controlled Responses/SSE data. This supports a separate loopback conformance test, not calling that test live model qualification.

Official references: https://developers.openai.com/codex/hooks/ and https://developers.openai.com/codex/config-reference/ (including their official redirects). These define supported configuration and lifecycle behavior; they do not promise model compliance with a specific test prompt.

## Repair

C09 now has one finite turn with three explicitly ordered read-only commands: **first -> second -> finish**. Each calls the installed product checkpoint/Git validator and fully reads canonical recovery inputs. The first two produce phase-specific inert high-volume stimuli; finish emits only a small receipt and requires the final structured result. No command calls hooks manually, changes canonical state, performs implementation work or reads qualification telemetry.

The outer fixture prepares its helper before bootstrap and seeds a hash-checked C09_FINITE_RECOVERY next action before the real checkpoint is created. Recovery and the initial request now describe the same task, not MAP_INSTRUCTIONS. Requested output budgets preserve the stimuli (65536 tokens); the disposable trigger is 8192 body-after-prefix tokens, no longer silently overwritten by the 200-token adapter. This threshold/workload separation leaves room for ordinary recovery and ending the turn. It is not a product configuration change or a claim that every model response is bounded below that threshold.

The evaluator strengthens, rather than relaxes, the gate: three successful exact commands/receipts; ordered automatic PreCompact -> PostCompact -> SessionStart(compact) cycles between the first/second/finish calls; successful product hook exit codes; real reconciliation after the second compaction; valid before/after checkpoint; unchanged source/planning Git **and file bytes including ignored state**; one completed positive structured C09 result. Timeout, missing context, extra/repeated/reordered/failed tools, unexpected tools, incomplete streams, reader or cleanup failure cannot pass. The 900-second live deadline is unchanged.

Fixture source and exact prompt are included in the manifest-validated evidence template. Only fixed phase labels, counts, booleans and codes are retained; neither private canonical contents nor raw transcripts are uploaded.

## Verification plan and limitations

Executable offline tests run actual installer/start/checkpoint/Git/hooks and the three fixture commands; only the model process is substituted in the offline driver. Negative cases cover stale checkpoint, wrong canonical action, byte changes missed by Git status, missing/manual/reordered lifecycle, repeated/failed/extra tools, incomplete completion and receipt validation.

A separate hosted conformance job downloads the exact official CLI release and verifies asset hashes. It runs the real CLI, real sandbox, tools and product hooks against a loopback Responses simulator, with no credentials or external model requests. The simulator selects responses and usage; passing demonstrates CLI integration, not autonomous live-model behavior. The normal offline suite does not require downloads or Codex.

Existing cross-platform product/harness suites, packaging, C10/C13 regression tests, evidence validation and release checks remain mandatory. The full model-backed C01-C16 workflow is the final qualification, not an outcome inferred from CI. No sandbox, approvals, auth ownership, product hook output, C13 fallback or release requirement is weakened.
