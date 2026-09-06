from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import shutil
import tarfile
from pathlib import Path, PurePosixPath

import qualification_c09 as c09

PART_GLOB = 'templates.part*'

C06_CODEX0152_OVERLAY = {
    'README.md': '''# C06 — PreToolUse plus deterministic mutation postcondition

- Source: `DOCUMENTED_AND_SOURCE_VERIFIED`
- Release-gating: `yes`
- Current result: `BLOCKED`
- Qualification package state: `READY_FOR_LIVE_RUN`
- Target runtime: Codex CLI `0.152.x`

## Objective

Verify the product boundary that Codex 0.152 actually exposes. A supported function-call `exec_command` must produce the canonical `Bash` `PreToolUse` event. File-changing transports that are not guaranteed to appear in the project hook stream remain fail-closed through PlanAnvil's deterministic Git/filesystem postcondition.

## Required live evidence

`REPRODUCED` requires both:

1. one real supported shell/`exec_command` call, at least one `PreToolUse` event with canonical tool name `Bash`, and no repository mutation;
2. one real direct file-change attempt that is either blocked by the hook boundary or detected immediately by the deterministic changed-path postcondition.

A missing `apply_patch` hook event is never evidence that a completed mutation is safe. Do not commit transcripts, credentials, private paths, or unrelated repository data.
''',
    'prompt.txt': '''Capability qualification C06: Codex 0.152 hook-plus-postcondition boundary.

Exercise the guaranteed `exec_command` -> canonical `Bash` PreToolUse adapter, then separately exercise one direct file-change attempt in a disposable fixture. The file-change attempt must either be blocked by the project hook or be detected by the deterministic Git/filesystem postcondition before any later mutation.

Do not execute hook scripts manually and do not treat missing hook telemetry as proof of safety.
''',
}

C13_BASELINE23_OVERLAY = {
    'README.md': '''# C13 — SubagentStart context semantics

- Source: `DOCUMENTED_AND_SOURCE_VERIFIED`
- Release-gating: `yes`
- Current result: `BLOCKED`
- Qualification package state: `READY_FOR_LIVE_RUN`
- Prepared: `2026-09-05`
- Baseline: `2.3`
- Target runtime: Codex CLI `0.153.4`; record the exact executed version

## Objective

Verify real project-scoped `SubagentStart` context injection and the documented non-blocking meaning of `continue=false`, separately from the known ephemeral parent-thread failure and from errors in the qualification proxy process.

Codex matches `SubagentStart` handlers against the spawned `agent_type`. The qualification child must therefore be spawned with `agent_type` exactly `fixture_agent`; a default or unnamed child is not equivalent.

## Baseline 2.3 transport

The v7 live harness attempts the explicitly declared project-scoped `fixture_agent` through `codex exec --ephemeral` first. Only the recognized `collab spawn failed: no thread with id` failure may activate a controlled non-ephemeral retry. That retry uses a separate disposable repository containing both the project-scoped agent and the project-scoped hook. Its disposable `CODEX_HOME` supplies persisted project trust and isolated runtime persistence, not a substitute agent or hook.

`REPRODUCED` requires one real project-scoped `SubagentStart`, `additionalContext`, a child echo of an outer-generated proof absent from the root prompt, unchanged repository state, verified session cleanup, and unchanged authentication metadata. `continue=false` is recorded as a compatibility signal but is not expected to stop `SubagentStart`.

The generated qualification proxy command must pass both required arguments: `SubagentStart subagent-start-fixture.py`. Offline process tests verify this contract but never constitute live capability evidence.

## Live metadata to record

Record the exact Codex version, model slug, OS, permission mode, persisted project trust, fixture commit, transport used, exact requested `agent_type`, setup/cleanup, sanitized observations, evaluation, and hashes. Do not commit transcripts, credentials, private paths, proof values, session IDs, or unrelated repository data.
''',
    'fixture/README.md': '''# C13 fixture

Both the ephemeral attempt and the recognized-error-only fallback use:
- project-scoped agent `.codex/agents/fixture_agent.toml`;
- explicit `[agents.fixture_agent]` with `config_file = "./agents/fixture_agent.toml"`;
- spawn request with `agent_type` exactly `fixture_agent`;
- project-scoped `SubagentStart` matcher `^fixture_agent$`;
- a proxy command with arguments `SubagentStart subagent-start-fixture.py`.

The fallback uses a separate disposable Git repository and an isolated CODEX_HOME. It does not materialize a home-scoped agent or hook. The sandbox remains read-only and repository state must remain unchanged. No manual invocation of the fixture hook can count as live evidence.
''',
    'fixture/agent-role.txt': '''Synthetic agent role: fixture_agent.
The real spawn request must set agent_type exactly to fixture_agent. Both transports declare the role in the project and keep SubagentStart project-scoped. The child echoes only context it actually received; the opaque value is absent from its own instructions and from the root prompt.
''',
    'config/README.md': '''# C13 sandbox configuration — baseline 2.3

Use the deterministic v7 live qualification harness rather than an interactive manual session.

```toml
[agents]
enabled = true
max_concurrent_threads_per_session = 2

[agents.fixture_agent]
description = "C13 qualification child for real SubagentStart context semantics."
config_file = "./agents/fixture_agent.toml"
```

- model: `gpt-5.6-sol`;
- approval: `never`;
- sandbox: `read-only`;
- model-tool network: disabled;
- project trust persisted in the disposable user config, never passed as a projects CLI override;
- real project-scoped agent and `SubagentStart` hook;
- filename/name/matcher: `fixture_agent.toml` / `fixture_agent` / `^fixture_agent$`;
- real spawn request uses `agent_type=fixture_agent`.

Transport is ephemeral-first. A non-ephemeral retry is allowed only for the recognized parent-thread registration failure. The retry uses a disposable CODEX_HOME, temporary file-backed auth symlink, isolated SQLite/log paths, history.persistence="none", mandatory cleanup, and auth-metadata verification. No home-scoped synthetic agent or hook substitutes for the project integration.
''',
    'prompt.txt': '''Capability qualification C13: real project-scoped SubagentStart context semantics.

Start exactly one configured child through the real Codex `spawn_agent` mechanism with `agent_type` exactly `fixture_agent`. Do not omit agent_type, do not use a default/unnamed child, do not simulate the child, and do not invoke hook scripts manually. The root session must not use command/file mutation tools.

The real project-scoped SubagentStart hook injects an opaque proof that is not present in this prompt and returns `continue=false`. This is a compatibility signal for the event, not a stop control. Wait for the real child and preserve only the minimal structural result needed to establish whether it received and echoed the injected proof.

Do not expose credentials, proof values, usernames, home directories, session/thread IDs, private repository URLs, or full transcripts.
''',
    'run-command.txt': '''# Targeted validation: existing workflow, branch main, mode=recovery (C09/C10/C13).
# Full release qualification: the same workflow, mode=full, after targeted validation.
python3 tools/live_codex_qualification_harness_v7.py \\
  --root <QUALIFICATION_REPO> \\
  --source-commit <FULL_MAIN_SHA> \\
  --run-id <RUN_ID> \\
  --output <SANITIZED_ARTIFACT_DIR> \\
  --allow-c13-non-ephemeral-fallback
# C13 always runs ephemeral first. Only the recognized parent-thread failure
# may activate the project-scoped non-ephemeral fallback.
''',
}

C09_COMPLETION_OVERLAY = {
    'fixture/README.md': """# C09 finite recovery fixture

The outer harness installs the unmodified product, prepares this fixture BEFORE bootstrap, replaces the bootstrap MAP_INSTRUCTIONS action with the hashed C09_FINITE_RECOVERY scenario, then creates and validates a real product checkpoint.

One Codex turn executes exactly three read-only commands: first, second, finish. Every command uses the actual installed checkpoint/Git validator and reads canonical recovery inputs. Only first and second emit bounded inert compaction stimuli. Finish emits a small receipt and ends the workload. No manual hook calls, synthetic live events, canonical writes during the turn, permission changes or repeated initial reads are permitted.

The trigger is 8192 body-after-prefix tokens; requested tool output budget is 65536 tokens for each stimulus. These are disposable fixture settings, not product defaults. The active compatibility layer must not replace this trigger with the old 200-token value. TokenBudget is disabled only in the existing isolated qualification configuration.

Require two ordered automatic PreCompact -> PostCompact -> SessionStart(source=compact) cycles, three successful canonical/Git reconciliations, real tool use after the second cycle, exact command order, valid checkpoints, unchanged source/planning files and Git, and one completed positive C09 turn. Timeout (still 900 seconds), extra/failed/repeated tools, missing recovery, failed hooks, reader/cleanup failures or incomplete evidence cannot be REPRODUCED. No raw output or private canonical state is persisted.

The fixed scenario resolves proven conflicting fixture instructions and removes an over-aggressive trigger. Historical #23 labels do not identify its exact commands, so the historical timeout's complete causal chain is not claimed as observed. Live success must still be established by the actual model-backed run.
""",
    'fixture/c09_probe.py': c09.PROBE_SOURCE,
    'prompt.txt': c09.prompt(),
    'run-command.txt': """# Existing controlled workflow: main -> recovery for C09/C10/C13, or full for C01-C16.
# Both select the identical C09 runtime; only full can satisfy the release gate.
python3 tools/live_codex_qualification_recovery.py --root <QUALIFICATION_REPO> --source-commit <FULL_MAIN_SHA> --run-id <RUN_ID> --output <SANITIZED_ARTIFACT_DIR> --allow-c13-non-ephemeral-fallback
# A loopback CLI conformance pass is offline and cannot count as live capability evidence.
""",
}


C10_ISOLATION_OVERLAY = {
    'README.md': """# C10 — Recovery context through SessionStart

- Source: `DOCUMENTED_AND_SOURCE_VERIFIED`
- Release-gating: `yes`
- Current result: `BLOCKED`
- Qualification package state: `READY_FOR_LIVE_RUN`
- Target runtime: Codex CLI `0.153.4`; record the executed version

Verify file/Git-based recovery at startup and immediately after genuine automatic compaction. The model-visible channel is SessionStart(source=compact), not PostCompact.additionalContext. PostCompact reports readiness using universal output fields. Canonical files/Git remain authoritative.

The two acceptance assertions remain unchanged. Exact opaque echo, actual lifecycle execution, no unauthorized tool reads, valid checkpoints, and source/planning immutability are mandatory. A declared model PASS without exact echo is not evidence of delivery.
""",
    'prompt.txt': """Exercise the installed PlanAnvil recovery handler at ordinary SessionStart and, independently, SessionStart(source=compact) after automatic compaction. PostCompact is a stateless advisory, not a context channel.

Use deterministic outer-harness fixtures and independent opaque targets. Never manually invoke a hook, read the target from files, invent it, or accept a model-declared PASS without an exact externally checked echo. Preserve source/planning state and checkpoint validity.
""",
    'fixture/README.md': """# C10 independent recovery fixtures

Prepare each fixture through the actual installer, product start command, checkpoint creator and checkpoint validator. The model must not construct its own prerequisites.

Startup and after-compaction probes use independent source repositories, planning worktrees and opaque next-action targets. Narrow SessionStart to ^compact$ in the second root checkout BEFORE the fixture commit and bootstrap. Do not remove this supported recovery channel. Codex 0.153.4 redirects linked-worktree hook declarations to the root checkout; changing only planning/.codex/hooks.json is not isolation.

Require PreCompact -> PostCompact -> SessionStart(source=compact), no ordinary startup record, a matching target actually emitted by the product, and an exact model echo without unauthorized file/tool reads. PostCompact emits a universal readiness advisory and no next-action target.

Keep source and planning state unchanged. Persist only boolean/hash-comparison results and bounded structural observations, never the opaque values. Offline drivers model only documented SessionStart context delivery; they do not constitute live capability evidence.
""",
    'config/README.md': """# C10 configuration provenance

Use the v7 runner live-auth/persisted-trust context. Do not copy or restore authentication tokens; restore runner config.toml byte-for-byte after the probe.

The startup fixture retains the product SessionStart hook. The independent after-compaction fixture retains PreCompact and PostCompact and narrows SessionStart to ^compact$ at the primary hook source. Check that the linked checkout has identical declarations. Prepare this BEFORE product snapshots/checkpoints. Model context comes only from SessionStart(source=compact), whose handler output is checked before examining the model echo.

Sandbox remains read-only, approval never, and model-tool network disabled. Low auto-compaction threshold and token_budget=false apply only to disposable fixtures, not product defaults. Preserve the process's bounded structural progress on timeout and kill its owned process group/tree before continuing the harness.
""",
    'run-command.txt': C09_COMPLETION_OVERLAY['run-command.txt'],
}



def _safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != 'capabilities':
        raise ValueError(f'unsafe capability template path: {name}')
    return path


def _rehash_capability(directory: Path) -> None:
    files = {}
    for path in sorted(directory.rglob('*')):
        if path.is_file() and path.name != 'hashes.json' and '__pycache__' not in path.parts:
            files[path.relative_to(directory).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    payload = {'schema_version': '1.0', 'algorithm': 'sha256', 'files': files}
    (directory / 'hashes.json').write_text(
        json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )


def _apply_overlay(target_root: Path, capability_id: str, overlay: dict[str, str]) -> list[str]:
    directory = target_root / 'capabilities' / capability_id
    if not directory.is_dir():
        raise FileNotFoundError(f'materialized {capability_id} package is missing')
    written = []
    for rel, text in overlay.items():
        target = directory / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
        written.append((Path('capabilities') / capability_id / rel).as_posix())
    _rehash_capability(directory)
    written.append(f'capabilities/{capability_id}/hashes.json')
    return written


def materialize(source_root: Path, target_root: Path, *, force: bool = False) -> list[str]:
    source_root = source_root.resolve()
    target_root = target_root.resolve()
    part_dir = source_root / 'capabilities'
    parts = sorted(part_dir.glob(PART_GLOB))
    if not parts:
        raise FileNotFoundError('capability template parts are missing')
    encoded = ''.join(part.read_text(encoding='ascii').strip() for part in parts)
    raw = base64.b64decode(encoded, validate=True)
    written: list[str] = []
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as tar:
        members = [m for m in tar.getmembers() if m.isfile()]
        for member in members:
            rel = _safe_member(member.name)
            target = target_root.joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = tar.extractfile(member)
            if payload is None:
                raise ValueError(f'missing template payload: {member.name}')
            data = payload.read()
            if target.exists() and not force and target.read_bytes() != data:
                raise FileExistsError(f'refusing to overwrite existing capability evidence: {target}')
            target.write_bytes(data)
            written.append(rel.as_posix())

    # Keep documentation synchronized without changing expected assertions or
    # synthesizing live results. Recompute hashes before package validation.
    written.extend(_apply_overlay(target_root, 'C06', C06_CODEX0152_OVERLAY))
    written.extend(_apply_overlay(target_root, 'C09', C09_COMPLETION_OVERLAY))
    written.extend(_apply_overlay(target_root, 'C10', C10_ISOLATION_OVERLAY))
    c10_expected_path = target_root / 'capabilities/C10/expected.json'
    c10_expected = json.loads(c10_expected_path.read_text(encoding='utf-8'))
    c10_expected['title'] = 'Recovery context via SessionStart at startup and after compaction'
    c10_expected_path.write_text(json.dumps(c10_expected, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    _rehash_capability(c10_expected_path.parent)
    written.extend(_apply_overlay(target_root, 'C13', C13_BASELINE23_OVERLAY))

    # The index and package guide are tracked outside the archive and are needed
    # when materializing into a disposable validation/sandbox root.
    for rel in (Path('capabilities/index.json'), Path('capabilities/README.md')):
        source = source_root / rel
        target = target_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != target.resolve():
            shutil.copyfile(source, target)
            written.append(rel.as_posix())
    return sorted(set(written))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Materialize prepared PlanAnvil C01-C16 live-evidence templates')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1], help='PlanAnvil source root')
    parser.add_argument('--target', type=Path, help='Target root; defaults to the source root')
    parser.add_argument('--force', action='store_true', help='Replace existing placeholder/template evidence files')
    args = parser.parse_args(argv)
    root = args.root.resolve()
    target = (args.target or root).resolve()
    written = materialize(root, target, force=args.force)
    print(f'Materialized {len(written)} capability template files under {target}.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
