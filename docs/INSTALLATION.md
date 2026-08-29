# Installing PlanAnvil

PlanAnvil 0.2.0 ships a standard-library distribution manager. It installs only the repository skill and the optional project-scoped Codex agents/hooks required by PlanAnvil. It does not edit product code, product tests, `AGENTS.md`, or unrelated Codex configuration.

## Requirements

- Python 3.11 or newer;
- Git 2.30 or newer;
- a Git repository with a clean worktree for normal install/upgrade/uninstall operations.

## Install from a checkout or release archive

From the PlanAnvil source/release root:

```text
python tools/plananvil_dist.py install --target /path/to/repository
```

Review the generated changes and commit them in the target repository. The installation records ownership in `.plananvil/installation.json` so later upgrades and uninstall operations can distinguish PlanAnvil-owned files from pre-existing files.

Verify at any time:

```text
python tools/plananvil_dist.py verify --target /path/to/repository
python tools/plananvil_dist.py status --target /path/to/repository
```

## Existing `.codex/config.toml`

The installer never replaces the file. It handles `[agents]` conservatively:

- existing compatible `enabled = true` is preserved;
- existing positive `max_concurrent_threads_per_session` or legacy `max_threads` is preserved;
- missing required keys are inserted inside a clearly marked PlanAnvil-managed block;
- a conflicting `enabled = false` or malformed concurrency value blocks installation instead of being overwritten.

Uninstall removes only the exact managed block recorded in installation state.

## Existing `.codex/hooks.json`

The installer parses JSON, preserves unrelated hook events/entries, and adds only the exact PlanAnvil hook entries from the release. A different unmanaged hook that already references `.codex/hooks/plan-anvil-*` is treated as a conflict and blocks installation.

Uninstall removes only the exact PlanAnvil entries recorded in installation state. Other hooks and other top-level JSON fields remain untouched.

## Existing `AGENTS.md`

PlanAnvil does not modify it. Codex instruction discovery remains the target repository's responsibility. The PlanAnvil skill explicitly reads applicable instructions during a run and records their complete hashes/scope in its instruction map.

## Upgrade

Use a newer PlanAnvil checkout or extracted release archive:

```text
python tools/plananvil_dist.py --source /path/to/new/plananvil upgrade --target /path/to/repository
```

Upgrade replaces a PlanAnvil-owned file only when its current hash still matches the hash recorded by the prior installation. Locally modified managed files cause a fail-closed conflict. Pre-existing identical files that were adopted rather than owned are never overwritten with different content.

## Uninstall

From any PlanAnvil checkout/release containing the distribution tool:

```text
python tools/plananvil_dist.py uninstall --target /path/to/repository
```

The command removes only unmodified PlanAnvil-owned files, the exact managed config block, exact PlanAnvil hook entries, and `.plananvil/installation.json`. It preserves adopted files and unrelated target-repository content.

## Dirty repositories

Normal operations require a clean worktree. `--allow-dirty` exists for controlled recovery/test scenarios, but it should not be the default installation workflow because it makes review of PlanAnvil's changes harder.

## Release archive integrity

Official release automation produces `plananvil-<version>.zip` and `SHA256SUMS`. Verify the archive checksum before extracting it, then use the installer above.
