# Codex capability evidence

This directory stores sanitized, reproducible evidence for the release gate in `docs/CODEX_CAPABILITY_BASELINE.md`.

The checked-in `C01`–`C16` packages and `index.json` contain reviewed live results from full run #25 (`34060321283`), source `d0384f76bc4150d33bb8f51ef5981f3243b3cfb3`. The exact original archive, summary and provenance are retained separately in `qualifications/34060321283/`. The historical C08 timeout and C13 fallback limitation are preserved, not edited out.

`capabilities/templates.part*` and the versioned materializer overlays create **fresh, unexecuted** C01–C16 packages. To inspect them without overwriting committed evidence:

```text
python tools/prepare_capabilities.py --target /path/to/disposable/templates --force
python tools/validate_capabilities.py --root /path/to/disposable/templates
```

The live workflow uses an isolated checkout and materializes in place there. Do not run in-place `--force` as a cleanup command in the checkout holding reviewed evidence. Materialization resets the index to the actual fresh package results (`BLOCKED`, `NOT_RUN`), never copying historical `REPRODUCED` labels onto new fixtures.

Each materialized package contains:

```text
CXX/
├── README.md
├── fixture/
├── prompt.txt
├── config/
├── run-command.txt
├── expected.json
├── actual.sanitized.json
├── evaluation.json
└── hashes.json
```

The prepared result is `BLOCKED`: it documents the fixture and the lack of live runtime evidence. `REPRODUCED` requires a real current Codex run with exact Codex version, model slug, OS, permission mode, project-trust mode, fixture commit, sanitized observations, evaluation, and SHA-256 integrity.

After reviewing new live evidence and updating its package (never rewrite an archived run):

```text
python tools/rehash_capability.py C01
python tools/validate_capabilities.py
```

Use `docs/CODEX_SANDBOX_RUNBOOK.md` for the full sequence. The materializer is path-traversal safe and writes only under `capabilities/`.

Do not commit session transcripts, credentials, usernames, home directories, temporary absolute paths, private repository URLs, session identifiers, unrelated Git databases, or proprietary source. Keep only the minimal structural event/decision data required to evaluate `expected.json`.
