# Codex sandbox qualification runbook

This is the remaining live-runtime step after deterministic/release hardening is complete.

## Sandbox prerequisites

- authenticated current Codex CLI/runtime;
- exact Codex version recorded before the first test;
- model slug recorded;
- operating system recorded;
- permission mode and project-trust mode recorded;
- Git available and target fixture repositories disposable;
- no real credentials, private repository URLs, personal paths, or proprietary source in fixtures/evidence.

Start the evidence branch by running:

```text
codex --version
python tools/prepare_capabilities.py --force
python tools/validate_capabilities.py
```

## Per-capability sequence

For C01 through C16 in order:

1. read `capabilities/CXX/README.md`;
2. instantiate the files described by `fixture/README.md` in a disposable Git repository;
3. apply the capability-specific configuration described in `config/README.md`;
4. execute the prompt in `prompt.txt` using the invocation recorded in `run-command.txt`;
5. capture only the structural observations required by `expected.json`;
6. sanitize the result into `actual.sanitized.json`;
7. set `evaluation.json` to `REPRODUCED`, `FAILED`, or `BLOCKED` based on the assertions;
8. when `REPRODUCED`, fill exact runtime metadata (`codex_version`, `model`, `os`, `permission_mode`, `project_trust`);
9. update the same result in `capabilities/index.json`;
10. run `python tools/rehash_capability.py CXX`;
11. run `python tools/validate_capabilities.py` before continuing.

C04 is informational/non-gating in baseline 2.2 but should still be observed if the sandbox exposes nested-subagent behavior relevant to future architecture.

## Sanitization

Do not commit session transcripts. Retain the minimum event/decision structure needed to evaluate assertions. Replace usernames, home directories, temporary absolute paths, repository URLs, IDs, credentials, and session identifiers with stable placeholders or hashes.

The validator rejects obvious token/private-path patterns in `actual.sanitized.json`.

## Final gate

When all required capabilities are `REPRODUCED`:

```text
python tools/validate_capabilities.py
python tools/release_check.py
```

Both must pass on a clean tree. Then merge the evidence PR, confirm protected `main` is green, and create the signed `v0.2.0` tag described in `docs/RELEASE.md`.
