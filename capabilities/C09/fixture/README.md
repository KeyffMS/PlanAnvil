# C09 finite recovery fixture

The outer harness installs the unmodified product, prepares this fixture BEFORE bootstrap, replaces the bootstrap MAP_INSTRUCTIONS action with the hashed C09_FINITE_RECOVERY scenario, then creates and validates a real product checkpoint.

One Codex turn executes exactly three read-only commands: first, second, finish. Every command uses the actual installed checkpoint/Git validator and reads canonical recovery inputs. Only first and second emit bounded inert compaction stimuli. Finish emits a small receipt and ends the workload. No manual hook calls, synthetic live events, canonical writes during the turn, permission changes or repeated initial reads are permitted.

The trigger is 8192 body-after-prefix tokens; requested tool output budget is 65536 tokens for each stimulus. These are disposable fixture settings, not product defaults. The active compatibility layer must not replace this trigger with the old 200-token value. TokenBudget is disabled only in the existing isolated qualification configuration.

Require two ordered automatic PreCompact -> PostCompact -> SessionStart(source=compact) cycles, three successful canonical/Git reconciliations, real tool use after the second cycle, exact command order, valid checkpoints, unchanged source/planning files and Git, and one completed positive C09 turn. Timeout (still 900 seconds), extra/failed/repeated tools, missing recovery, failed hooks, reader/cleanup failures or incomplete evidence cannot be REPRODUCED. No raw output or private canonical state is persisted.

The fixed scenario resolves proven conflicting fixture instructions and removes an over-aggressive trigger. Historical #23 labels do not identify its exact commands, so the historical timeout's complete causal chain is not claimed as observed. Live success must still be established by the actual model-backed run.
