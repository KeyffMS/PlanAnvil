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

For the current C08 closure, use a NEW `mode=full` run on main, initiated by an account allowed by the self-hosted runner. The production validator requires a single complete full-run archive containing the finite C08 proof. A successful `c08` or `recovery` diagnostic is useful but its partial archive cannot replace that full run. See `docs/QUALIFICATION_STATUS.md` for the merged repair and the automated launch rejected before testing.

## Publish

`VERSION` is the canonical distribution/release version. The deterministic artifact generator version is recorded independently in generated artifacts for compatibility. A production tag must be exactly `v<VERSION>`.

After live qualification is merged and `main` is green:

```text
git tag -s v0.2.0 -m "PlanAnvil 0.2.0"
git push origin v0.2.0
```

`.github/workflows/release.yml` reruns the deterministic gates, requires all release-gating capabilities to be `REPRODUCED`, builds a deterministic ZIP + checksum, and creates the GitHub Release. It cannot publish while capability evidence remains blocked.

Before any release artifact is built, the tag workflow also fails closed unless:

- the pushed tag is an annotated tag object rather than a lightweight tag;
- GitHub reports the tag signature as cryptographically verified;
- the tag points directly to a commit;
- the tagged commit is reachable from `origin/main`;
- the checked-out release tree is clean, including untracked files.

The production `release_check.py` enforces clean-tree state in addition to version, changelog, distribution manifest, release-file and live capability gates. Candidate mode intentionally skips the live-evidence and clean-production-tree requirements so ordinary PR CI remains usable.

## Repository administration prerequisite

Before production release, protect `main` as tracked in issue #6: PR-only changes, required CI, up-to-date branch, conversation resolution, and no force push/delete.

## Qualification closure (2026-09-07)

The baseline #25 evidence is preserved immutably. `qualifications/index.json`
identifies the current reviewed full run; its source SHA always remains the
actually executed commit, never the later evidence-import commit.
`release_check.py` also validates the original archive digest/manifest, exact
current capability packages, qualified .agents/.codex bytes, and finite C08
negative-stop/positive-completion evidence. The old C08 timeout keeps production
blocked until the new complete full-run result is committed. Candidate checks
intentionally remain usable before that result exists.

To import a successful new full result, preserve its exact archive, summary and
verified provenance under `qualifications/<run-id>/`, import its exact C01-C16
packages, and point `qualifications/index.json.current_run` to that run. Keep the
original #25 archive and provenance unchanged. Never merge a partial index into
the full index, edit old actual observations, or label the denied automated launch
as tested. Validate archive integrity and production readiness on the resulting
clean tree through a protected PR before any signed publication.

The active main ruleset was verified on 2026-09-07: PR-only squash changes,
seven required status checks, strict up-to-date branch, conversation resolution,
no deletion or force push, no bypass actors. The protected distribution job now
also requires real-CLI conformance to succeed. No policy is loosened for closure.

After the complete new full-run evidence is imported and CI is green, preparation
is complete; the signed annotated production tag remains a separate authorized
publication. No unsigned or lightweight tag may substitute for the required
verified signature.
