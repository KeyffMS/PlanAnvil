# Codex sandbox qualification runbook

This is the remaining live-runtime step after deterministic/release hardening is complete.

## Sandbox prerequisites

- authenticated current Codex CLI/runtime;
- exact Codex version recorded before the first test;
- model slug recorded;
- operating system recorded;
- permission mode and project-trust mode recorded;
- Git available and target fixture repositories disposable;
- system `bubblewrap` installed on Linux (`apt install bubblewrap` on Debian/Ubuntu);
- Linux user-namespace creation must work from the runner process;
- no real credentials, private repository URLs, personal paths, or proprietary source in fixtures/evidence.

On a Podman-hosted runner, Codex creates an inner Linux command sandbox. The outer container must therefore permit the runner user to create the user namespace required by `bwrap`. Before a full qualification run, this probe must succeed inside the runner container:

```text
command -v bwrap
bwrap --unshare-user --uid 0 --gid 0 --ro-bind / / /bin/true
```

If the probe fails with `setting up uid map: Operation not permitted`, fix the Podman/host user-namespace policy rather than disabling Codex sandboxing. The qualification workflow deliberately does not use `danger-full-access` or `--dangerously-bypass-approvals-and-sandbox`.

## Controlled GitHub Actions path

The preferred qualification path is `.github/workflows/plananvil-codex-qualification.yml`. The workflow is intentionally `workflow_dispatch`-only, accepts execution only from `main`, uses Environment `plananvil-codex`, and targets `[self-hosted, linux, x64, plananvil, codex]`.

Use `mode=full` for the release-gating C01-C16 sequence. `mode=c13` remains available as a shorter C13-only probe, but it is not a substitute for the full release gate.

The controlled runner must provide `plananvil-qualification-workspace`. The workflow creates a disposable workspace with that helper, fetches only the exact dispatched `main` SHA, materializes the C01-C16 evidence templates, and runs `tools/live_codex_qualification_harness_v7.py`. Model `gpt-5.6-sol` is pinned, approval policy remains `never`, model-tool network access is disabled, and `workspace-write` is granted only to disposable fixture roots when a trial requires it. Vetted project hooks may bypass only the interactive hook-trust prompt; approval and filesystem sandboxing remain enabled.

For C08/C09, Codex 0.152 project trust remains a persisted user-config setting, but long full runs must use the runner's real `CODEX_HOME` so the CLI can refresh live authentication normally. The harness temporarily appends only the disposable fixture trust entry to the runner's `config.toml`, removes the invalid CLI trust path, and restores `config.toml` byte-for-byte after the capability. Authentication/session files are not copied or replaced by this trust bridge.

All normal agent tasks remain ephemeral. Baseline 2.3 introduces exactly one transport exception for C13: the harness may retry C13 non-ephemerally only when the first real ephemeral attempt matches the recognized `collab spawn failed: no thread with id` parent-thread registration error. Any other ephemeral blocker remains `BLOCKED` and does not activate the exception.

### C13 baseline 2.3 transport

C13 tests the documented `SubagentStart` semantics, not persistence of `codex exec --ephemeral`.

The first C13 attempt is a real project-scoped configuration. The synthetic agent file is `.codex/agents/fixture_agent.toml`, `[agents.fixture_agent]` points to that file, the prompt requests `fixture_agent`, and the project-scoped `SubagentStart` matcher targets the same name. The hook injects an outer-generated opaque context proof and intentionally returns `continue=false`.

If and only if that ephemeral attempt hits the recognized parent-thread registration failure, the harness creates a second disposable Git repository and retries non-ephemerally. The fallback remains product-aligned: the synthetic agent is still project-scoped, explicitly declared as `[agents.fixture_agent]`, and the real `SubagentStart` hook remains project-scoped. The disposable `CODEX_HOME` is used only for the fixture trust decision, file-backed authentication bridge, and isolated non-ephemeral persistence.

The non-ephemeral retry preserves all security boundaries:

- C13 remains `read-only`;
- approval remains `never`;
- model-tool network access remains disabled;
- the Git repository is disposable and explicitly trusted only for the trial;
- the root C13 session may not use command/file mutation tools;
- file-backed authentication is bridged only by a temporary symlink to the existing `auth.json`; the harness does not read or copy its contents;
- SQLite and log paths are redirected into the disposable `CODEX_HOME`;
- message history persistence is disabled;
- the entire disposable `CODEX_HOME` is removed after the retry;
- the authenticated source `auth.json` metadata must remain unchanged;
- evidence retains only structural counts/booleans and never session/thread IDs or the opaque proof value.

C13 is `REPRODUCED` only when exactly one real project-scoped `SubagentStart` hook event occurs, that hook returns both `additionalContext` and `continue=false`, and the real project-scoped child returns the unseen injected proof. If the semantic boundary is reached but the child lacks the context or startup is stopped by `continue=false`, the result is `FAILED`. If the semantic boundary is not reached or cleanup/auth isolation cannot be proved, the result is `BLOCKED`.

The transport correction is deliberately narrow. It does not move PlanAnvil roles or hooks into user configuration, does not treat a home-scoped synthetic role as product-equivalent, and does not weaken sandbox, approval, trust, network, source-immutability, or evidence-sanitization requirements.

## Evidence and sanitization

Raw Codex session streams are not retained. The controller keeps only sanitized final assertions, event-type counts, hashes and relative Git structure required for evaluation. The self-hosted runner has repository read permission only and never pushes qualification changes.

The workflow performs the Linux `bubblewrap` user-namespace probe before preparing fixtures, so an incompatible container fails in seconds instead of consuming a live qualification run. It uploads `plananvil-codex-evidence-<run-id>` as a short-lived artifact. Review that artifact before committing evidence through a normal protected pull request. A `full` workflow run exits successfully only when every release-gating capability is `REPRODUCED`; partial/failed runs still upload their sanitized evidence artifact for diagnosis.

Do not commit session transcripts. Retain the minimum event/decision structure needed to evaluate assertions. Replace usernames, home directories, temporary absolute paths, repository URLs, IDs, credentials and session identifiers with stable placeholders or hashes.

The validator rejects obvious token/private-path patterns in `actual.sanitized.json`.

## Manual fallback

For an equivalent manual run in a dedicated sandbox:

```text
codex --version
python tools/prepare_capabilities.py --force
python tools/validate_capabilities.py
```

The release-gating controller invocation must include the baseline 2.3 C13 transport permission:

```text
python tools/live_codex_qualification_harness_v7.py \
  --source-commit <FULL_MAIN_SHA> \
  --run-id <RUN_ID> \
  --output <SANITIZED_ARTIFACT_DIR> \
  --allow-c13-non-ephemeral-fallback
```

The flag is only permission for the narrow fallback. It does not force non-ephemeral execution; C13 always attempts ephemeral execution first.

## Per-capability sequence

For C01 through C16 in order:

1. read `capabilities/CXX/README.md`;
2. instantiate the files described by the prepared capability package in a disposable Git repository;
3. apply the capability-specific deterministic harness setup where the current controller defines one;
4. execute the live trial using the least-privilege sandbox required by that capability;
5. capture only the structural observations required by the capability assertion;
6. sanitize the result into `actual.sanitized.json`;
7. set `evaluation.json` to `REPRODUCED`, `FAILED`, or `BLOCKED` based on the assertions;
8. when `REPRODUCED`, fill exact runtime metadata (`codex_version`, `model`, `os`, `permission_mode`, `project_trust`);
9. update the same result in `capabilities/index.json`;
10. run `python tools/rehash_capability.py CXX`;
11. run `python tools/validate_capabilities.py` before continuing.

C04 is informational/non-gating in baseline 2.3 but should still be observed if the sandbox exposes nested-subagent behavior relevant to future architecture.

## Final gate

When all required capabilities are `REPRODUCED`:

```text
python tools/validate_capabilities.py
python tools/release_check.py
```

Both must pass on a clean tree. Then merge the evidence PR, confirm protected `main` is green, and create the signed `v0.2.0` tag described in `docs/RELEASE.md`.
