# Codex capability evidence

This directory stores sanitized, reproducible evidence for the release gate in `docs/CODEX_CAPABILITY_BASELINE.md`.

A capability is not `REPRODUCED` until its directory contains:

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

Record the exact Codex version, model slug, operating system, permission mode, project-trust mode, fixture commit, setup, cleanup, expected behavior, sanitized actual behavior, and evaluation. Remove usernames, home directories, private repository URLs, credentials, session identifiers, transcripts, unrelated Git databases, and proprietary source.

The repository ships deterministic contract tests and evidence scaffolding, but does not label live Codex behavior as reproduced without these packages.
