# PlanAnvil

PlanAnvil is a Codex-native repository skill that turns a software-engineering goal into a rigorous, test-driven, auditable implementation contract.

It **generates and validates a plan but never executes it**. Product implementation happens only in a separate later Codex run using the execution prompt written into `PLAN.md`.

## Status

**Distribution version:** 0.2.0.

The deterministic generator core, schemas, templates, tests, optional planning agents, defense-in-depth hooks, repository installer/upgrader/uninstaller, release tooling, and a deterministic C01-C16 live-qualification template archive/materializer are implemented.

**Full baseline 2.3 qualification passed:** run [#25](https://github.com/KeyffMS/PlanAnvil/actions/runs/34060321283) reproduced C01–C16 on source commit `d0384f76bc4150d33bb8f51ef5981f3243b3cfb3`, with Codex CLI `0.153.4`, model `gpt-5.6-sol`, and Debian 13. C04 is informational; the other fifteen capabilities gate qualification. The complete sanitized evidence is committed under `capabilities/` and preserved unchanged under `qualifications/34060321283/`.

**Release status remains candidate.** The old C08 positive trial proved its narrow unblock assertion but later timed out. Its finite replacement must finish in a new live `mode=c08` run and its evidence must be committed before production publication. C13 was reproduced through the explicit known-error-gated non-ephemeral fallback, not by proving ephemeral spawning works.

See [current qualification and release status](https://github.com/KeyffMS/PlanAnvil/blob/main/docs/QUALIFICATION_STATUS.md) for the precise evidence boundary and next step. Deterministic CI and loopback CLI conformance are regression checks, not substitutes for live model evidence. Production publication also retains protected-main, clean-tree and verified signed annotated-tag requirements.

The capability contract is defined in `docs/CODEX_CAPABILITY_BASELINE.md`.

## Install into another repository

From a PlanAnvil checkout or extracted release archive:

```text
python tools/plananvil_dist.py install --target /path/to/repository
```

The installer:

- copies the PlanAnvil skill and project-scoped agent/hook files;
- preserves an existing `AGENTS.md` unchanged;
- conservatively merges compatible `[agents]` settings instead of replacing `.codex/config.toml`;
- structurally merges only PlanAnvil entries into `.codex/hooks.json` while preserving unrelated hooks;
- records file ownership/hashes in `.plananvil/installation.json`;
- fails closed on unmanaged conflicts or locally modified managed files.

Verify, upgrade, or uninstall:

```text
python tools/plananvil_dist.py verify --target /path/to/repository
python tools/plananvil_dist.py --source /path/to/new/release upgrade --target /path/to/repository
python tools/plananvil_dist.py uninstall --target /path/to/repository
```

See `docs/INSTALLATION.md` for the ownership and conflict contract.

## Use

The repository skill is discovered from:

```text
.agents/skills/plan-anvil/
```

Implicit invocation is disabled. Invoke it explicitly:

```text
$plan-anvil Generate a plan to add validation that rejects an empty display name.
```

A run must:

1. verify a clean source worktree;
2. run a real reversible Git ref, branch, worktree, index, and commit probe;
3. create an isolated planning branch and external linked worktree;
4. preserve schema-validated Git/lifecycle bootstrap evidence;
5. profile the repository, map complete applicable instructions, and record immutable goal analysis;
6. author stable plan, stage, risk, control, and traceability artifacts;
7. pass deterministic validation and immutable blind review;
8. commit planning artifacts only;
9. report the result and stop without implementing anything.

The deterministic controller can also be inspected directly:

```text
python .agents/skills/plan-anvil/scripts/plan_anvil.py start \
  --source . \
  --goal "Add validation that rejects an empty display name."
```

## Safety boundary

PlanAnvil does not modify application code or tests, execute generated stages, deploy, migrate, restart services, switch a live environment, use destructive Git cleanup, or push or merge the base branch.

The retained planning worktree is the durable control root. Machine-specific paths remain only in ignored local files; committed artifacts use repository-relative paths and Git identity.

Project-scoped `.codex` agents and hooks remain defense in depth; mandatory filesystem and Git postconditions apply in every hook mode.

## Requirements

- Python 3.11 or newer;
- Git 2.30 or newer;
- no elevated privileges;
- no third-party Python packages for deterministic core/distribution tooling;
- no network access for local validation or installation.

CI tests Python 3.11 and the current upper supported interpreter on Ubuntu, macOS, and Windows. Parser/preflight tests enforce the Git 2.30 minimum; live Codex C16 remains responsible for the permission-mode Git capability matrix.

## Validation

```text
python -m unittest discover -s .agents/skills/plan-anvil/tests -v
python -m unittest discover -s tests -v
python -m compileall -q .agents/skills/plan-anvil .codex/hooks tools tests
python tools/release_check.py --candidate
```

## Release and live qualification

- `docs/RELEASE.md` — deterministic gates, tag workflow and publication contract
- `docs/CODEX_SANDBOX_RUNBOOK.md` — current full and targeted sandbox procedures
- `capabilities/templates.part*` + `tools/prepare_capabilities.py` — deterministic prepared C01-C16 fixtures/prompts/config/assertions/results/hashes

A production tag is rejected by `.github/workflows/release.yml` until every required capability is `REPRODUCED`.

## Documentation

- `docs/IMPLEMENTATION_SPEC.md` — authoritative product and implementation contract
- `docs/ARCHITECTURE.md` — architecture and trust boundaries
- `docs/ARTIFACT_SCHEMAS.md` — canonical state and artifact formats
- `docs/RECOVERY_AND_VALIDATION.md` — crash recovery, checkpoint, schema and path-safety guarantees
- `docs/OPENAI_COMPLIANCE.md` — Codex compatibility decisions
- `docs/CODEX_CAPABILITY_BASELINE.md` — reproducible capability release gate
- `docs/QUALIFICATION_STATUS.md` — current qualification status and historical audit index
- `docs/INSTALLATION.md` — install/upgrade/uninstall contract
- `docs/TROUBLESHOOTING.md` — operational recovery guidance
- `docs/RELEASE.md` — release workflow
- `docs/CODEX_SANDBOX_RUNBOOK.md` — live qualification procedure

## Author

[KeyffMS](https://github.com/KeyffMS) / [aiteracja.pl](https://aiteracja.pl)
