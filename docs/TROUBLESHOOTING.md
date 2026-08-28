# Troubleshooting

## Installer reports a conflicting file

PlanAnvil refuses to overwrite an unmanaged file at a path it owns. Compare the target file with the release payload. Rename/remove it deliberately, or keep the current file and do not install that PlanAnvil release.

## Installer reports modified managed files during upgrade/uninstall

The file no longer matches `.plananvil/installation.json`. Preserve/review the local modification first. PlanAnvil intentionally does not overwrite or delete it automatically.

## Existing `[agents]` configuration conflicts

PlanAnvil requires agents to be enabled for its reviewer/profiler workflow. If the repository explicitly sets `enabled = false`, decide at repository-policy level whether PlanAnvil agents are permitted; the installer will not flip the setting automatically.

## Existing hooks conflict

A hook referencing `.codex/hooks/plan-anvil-*` but differing from the release is ambiguous ownership. Reconcile or remove the old PlanAnvil hook entry before installing/upgrading.

## `verify` reports a hash mismatch

A managed or adopted payload file changed after installation. Compare it with the release/source version and either restore it or intentionally reconcile it before upgrade/uninstall.

## Capability gate is `BLOCKED`

That is expected until the live Codex sandbox is available. Deterministic CI, distribution tests, and capability package validation do not substitute for live `REPRODUCED` evidence. Follow `docs/CODEX_SANDBOX_RUNBOOK.md` once an authenticated Codex runtime is available.

## GitHub release workflow refuses to publish

`tools/release_check.py` is intentionally fail-closed. A stable tag can publish only when every capability marked `required` in `capabilities/index.json` is `REPRODUCED`, all evidence packages validate, the tag matches `VERSION`, and the distribution manifest is complete.
