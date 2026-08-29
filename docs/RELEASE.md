# Release process

PlanAnvil release engineering is split into deterministic readiness and live Codex qualification.

## Deterministic readiness

The normal CI workflow verifies:

1. core compile + unit/integration suite on Ubuntu, macOS, and Windows;
2. Python 3.11 (minimum) and the current tested upper interpreter;
3. distribution install/verify/upgrade/uninstall behavior;
4. deterministic materialization plus structural/SHA-256 integrity of the prepared C01-C16 template archive;
5. release-candidate metadata and deterministic archive construction.

Run locally:

```text
python -m unittest discover -s .agents/skills/plan-anvil/tests -v
python -m unittest discover -s tests -v
python tools/release_check.py --candidate
python tools/build_release.py --output dist
```

## Live Codex gate

Before a production tag, execute `docs/CODEX_SANDBOX_RUNBOOK.md`. Required entries in `capabilities/index.json` must be changed from `BLOCKED` to `REPRODUCED` only after their complete sanitized evidence package is committed and `python tools/validate_capabilities.py` passes.

## Publish

`VERSION` is the canonical distribution/release version. The deterministic artifact generator version is recorded independently in generated artifacts for compatibility. A production tag must be exactly `v<VERSION>`.

After live qualification is merged and `main` is green:

```text
git tag -s v0.2.0 -m "PlanAnvil 0.2.0"
git push origin v0.2.0
```

`.github/workflows/release.yml` reruns the deterministic gates, requires all release-gating capabilities to be `REPRODUCED`, builds a deterministic ZIP + checksum, and creates the GitHub Release. It cannot publish while capability evidence remains blocked.

## Repository administration prerequisite

Before production release, protect `main` as tracked in issue #6: PR-only changes, required CI, up-to-date branch, conversation resolution, and no force push/delete.
