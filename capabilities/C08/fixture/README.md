# Finite C08 stop/repair qualification

Use the real product in one canonical planning run. Prepare the C08_FINITE_RECOVERY
state before checkpoint creation. The negative invocation executes pressure once
and must terminate at the real PreCompact stop with a missing checkpoint.
The outer harness then creates a real valid checkpoint; the repaired invocation
executes pressure -> automatic compaction -> SessionStart(compact) -> finish and
must terminate with positive structured output, without timeout or extra tools.
Startup recovery is excluded at the primary root-checkout hook source before
bootstrap; the actual compact recovery handler remains installed. No product
hook is bypassed, manually invoked by the live model, or replaced with a mock.
Require ordered receipts, real product validation, complete process diagnostics,
checkpoint validity before/after, and source/planning Git and file-byte immutability.
The 8192 token trigger and 65536 output allowance belong only to this fixture.
Both original C08 assertions remain mandatory. The 600-second limit is unchanged.
