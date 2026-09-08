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

Current full run #27 (`34140846679`) passed and its exact reviewed evidence is committed, including finite C08 stop/repair completion. No further live run is required merely to record this result. The production validator still requires one complete full-run archive; a `c08` or `recovery` diagnostic cannot replace it. See `docs/QUALIFICATION_STATUS.md` for provenance, tested scope and the retained C13 fallback limitation.

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

## Qualification closure (reviewed 2026-09-08)

The baseline #25 evidence is preserved immutably. `qualifications/index.json`
identifies the current reviewed full run; its source SHA always remains the
actually executed commit, never the later evidence-import commit.
`release_check.py` also validates the original archive digest/manifest, exact
current capability packages, qualified .agents/.codex bytes, and finite C08
negative-stop/positive-completion evidence. Full #27 now supplies that proof;
the old #25 timeout remains recorded as history. Candidate checks still do not
substitute for strict production validation. Run `python tools/release_check.py`
on the clean evidence-import commit before any signed publication.

To import a successful new full result, preserve its exact archive, summary and
verified provenance under `qualifications/<run-id>/`, import its exact C01-C16
packages, and point `qualifications/index.json.current_run` to that run. Keep the
original #25 archive and provenance unchanged. Never merge a partial index into
the full index, edit old actual observations, or label the denied automated launch
as tested. Validate archive integrity and production readiness on the resulting
clean tree through a protected PR before any signed publication.

The active main ruleset was reverified on 2026-09-08: PR-only squash changes,
seven required status checks, strict up-to-date branch, conversation resolution,
no deletion or force push, no bypass actors. The protected distribution job now
also requires real-CLI conformance to succeed. No policy is loosened for closure.

The complete #27 evidence is imported. After strict validation and green CI on
the evidence-import commit, qualification preparation is complete; a signed
annotated production tag remains a separate authorized publication. This import
does not create a tag or release. No unsigned or lightweight tag may substitute
for the required verified signature.

## Remaining publication steps and follow-up

All changes intended for the first 0.2.0 publication are grouped under its
pending-publication section in `CHANGELOG.md`. `VERSION` remains 0.2.0;
qualification reconciliation alone does not change the distribution version.

Before tagging, merge the documentation reconciliation through protected CI,
run strict release validation on the resulting clean checkout, and use the
verified signed annotated-tag procedure above. The current qualification
metadata and C08 compliance checkbox are compared with the archived summary
and index by `tests/test_qualification_documentation.py` in PR and release CI.

The baseline 2.3 contract and full #27 evidence resolve the C13 qualification
question in [issue #17](https://github.com/KeyffMS/PlanAnvil/issues/17).
Ephemeral custom-agent spawning remains a documented compatibility limitation;
requalify it when the upstream runtime changes.

[Issue #37](https://github.com/KeyffMS/PlanAnvil/issues/37) remains open for
hosted C09 receipt-observer reliability. It does not invalidate the separate
full #27 proof. Future Codex/model/OS support needs scoped requalification.
Plugin packaging remains outside v1 under `IMPLEMENTATION_SPEC.md`.
