# Codex capability evidence

This directory stores sanitized, reproducible evidence for the release gate in `docs/CODEX_CAPABILITY_BASELINE.md`.

`capabilities/templates.part*` contains deterministic prepared C01-C16 packages. Before a live qualification run, materialize them on the evidence branch:

```text
python tools/prepare_capabilities.py --force
python tools/validate_capabilities.py
```

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

After editing one capability:

```text
python tools/rehash_capability.py C01
python tools/validate_capabilities.py
```

Use `docs/CODEX_SANDBOX_RUNBOOK.md` for the full sequence. The materializer is path-traversal safe and writes only under `capabilities/`.

Do not commit session transcripts, credentials, usernames, home directories, temporary absolute paths, private repository URLs, session identifiers, unrelated Git databases, or proprietary source. Keep only the minimal structural event/decision data required to evaluate `expected.json`.
