# Codex sandbox qualification runbook

This is the remaining live-runtime step after deterministic/release hardening is complete.

## Sandbox prerequisites

- authenticated current Codex CLI/runtime; baseline 2.2 qualification currently requires Codex CLI `>= 0.150.1`;
- exact Codex version recorded before the first test;
- model slug recorded;
- operating system recorded;
- permission mode and project-trust mode recorded;
- Git available and target fixture repositories disposable;
- system `bubblewrap` installed on Linux (`apt install bubblewrap` on Debian/Ubuntu);
- Linux user/PID namespace creation and a fresh `/proc` mount must work from the runner process;
- no real credentials, private repository URLs, personal paths, or proprietary source in fixtures/evidence.

On a Podman-hosted runner, Codex creates an inner Linux command sandbox. The outer container must therefore permit the runner user to create the namespaces and mounts required by `bwrap`. Before a full qualification run, this probe must succeed inside the runner container:

```text
command -v bwrap
bwrap --unshare-user --unshare-pid --uid 0 --gid 0 --ro-bind / / --proc /proc /bin/true
```

If the probe fails with `setting up uid map: Operation not permitted`, fix the Podman/host user-namespace policy rather than disabling Codex sandboxing. If it fails while mounting `/proc`, inspect Podman's masked-path policy and selectively `unmask` only the proc submounts required by the inner sandbox. Do not replace the default seccomp profile with `unconfined`, do not enable `privileged`, and do not use `--dangerously-bypass-approvals-and-sandbox` for qualification.

Codex CLI 0.150.1 includes a Linux sandbox preflight/fallback for restrictive environments that deny a fresh `/proc` mount. Older runtimes such as 0.144.1 are not accepted for the current live baseline because they can fail capability trials before the requested tool command executes.

## Controlled GitHub Actions path

The preferred qualification path is `.github/workflows/plananvil-codex-qualification.yml` in `full` mode. The workflow is intentionally `workflow_dispatch`-only, accepts execution only from `main`, uses Environment `plananvil-codex`, and targets `[self-hosted, linux, x64, plananvil, codex]`.

The controlled runner must provide `plananvil-qualification-workspace`. The workflow creates a disposable workspace with that helper, fetches only the exact dispatched `main` SHA, then performs a real Codex tool-sandbox probe that requires a successful shell `command_execution` under `read-only`, `approval_policy=never`, and disabled model-tool network access. Only after that probe succeeds does it materialize the C01-C16 evidence templates and run `tools/live_codex_qualification.py` sequentially.

The controller invokes every agent task through `codex exec --ephemeral`, pins model `gpt-5.6-sol`, uses approval policy `never`, disables network access for model-generated commands, and grants `workspace-write` only to disposable fixture roots when a trial requires writes. Vetted project hooks may bypass the interactive hook-trust prompt; approval and filesystem sandboxing remain enabled.

Raw Codex session streams are not retained. The controller keeps only sanitized final assertions, event-type counts, and relative Git structure required for evaluation. The self-hosted runner has repository read permission only and never pushes qualification changes.

The workflow performs the Linux `bubblewrap` namespace/proc probe and the actual Codex command-sandbox probe before preparing fixtures, so an incompatible container or stale CLI fails in seconds instead of consuming a full C01-C16 run. It uploads `plananvil-codex-evidence-<run-id>` as a short-lived artifact. Review that artifact before committing evidence through a normal protected pull request. A full workflow run exits successfully only when every release-gating capability is `REPRODUCED`; partial/failed runs still upload their sanitized evidence artifact for diagnosis.

## Manual fallback

For an equivalent manual run in a dedicated sandbox:

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
