# Artifact contract

## Run layout

`.pursue/runs/<TIMESTAMP>_<PLAN-ID>_<SLUG>/` contains `PLAN.md`, `manifest.json`, `state.json`, `compliance.json`, `traceability.json`, ignored `local-state.json`, and the `stages`, `checkpoints`, `reports`, `risks`, `evidence`, `diffs`, `logs`, `incidents`, and `final` directories.

Canonical machine state is JSON. Markdown is human-readable and never overrides JSON. Bootstrap evidence includes `evidence/git-capability.json` and `evidence/lifecycle.json`; goal analysis uses immutable `evidence/analysis.md` and `.json`.

## Canonical conventions

- UTF-8, LF, sorted keys, two-space indentation, terminal newline
- schema version `1.1.0`
- RFC 3339 UTC timestamps
- SHA-256 values prefixed with `sha256:`
- unknown fields rejected unless explicitly allowed
- atomic replacement for mutable state
- monotonic `state.json.revision`
- exactly one `next_action`
- immutable checkpoints and blind-review artifacts

## Privacy

Committed artifacts must not contain absolute local paths, usernames, machine-specific services, credentials, private keys, cookies, copied `.env` data, or private repository URLs.

Machine-specific locators belong only in ignored:

- `.pursue/SYSTEM_PROFILE.local.md`
- `.pursue/runs/<RUN-ID>/local-state.json`

Validators must prove these files are ignored and untracked.

## Path safety

Resolve every write, reject traversal, symlink escapes, `.git` writes outside dedicated Git commands, case-insensitive escapes, and submodule writes not explicitly in scope. Match allowlists using repository-relative POSIX paths.

## Goal analysis

`evidence/analysis.md` and `evidence/analysis.json` are immutable analysis inputs. The JSON records the goal hash, classification, risk, affected paths, evidence, assumptions, unknowns, and Markdown hash. A critical unknown transitions the run to `BLOCKED_BY_CRITICAL_UNKNOWN`.
