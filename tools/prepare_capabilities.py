from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import shutil
import tarfile
from pathlib import Path, PurePosixPath

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
- Prepared: `2026-09-03`
- Baseline: `2.3`
- Target runtime: Codex CLI `0.152.x`

## Objective

Verify real `SubagentStart` context injection and the documented non-blocking meaning of `continue=false` without conflating those semantics with independent ephemeral parent-thread registration or project-scoped synthetic-agent discovery limitations.

Codex 0.152 matches `SubagentStart` handlers against the spawned `agent_type`. The qualification child must therefore be spawned with `agent_type` exactly `fixture_agent`; a default or unnamed child is not equivalent.

## Baseline 2.3 transport

The live harness attempts the aligned project-scoped `fixture_agent` through `codex exec --ephemeral` first. Only the recognized `collab spawn failed: no thread with id` failure may activate a controlled non-ephemeral retry. That retry uses a separate disposable repository containing the project-scoped hook/config but no project-scoped synthetic agent; the child is materialized as `CODEX_HOME/agents/fixture_agent.toml` inside a disposable `CODEX_HOME`.

`REPRODUCED` still requires one real project-scoped `SubagentStart`, `additionalContext`, a child echo of an outer-generated proof absent from the root prompt, unchanged repository state, verified session cleanup, and unchanged authentication metadata. `continue=false` is recorded as a compatibility signal but is not expected to stop `SubagentStart` on Codex 0.152.

## Live metadata to record

Before changing this result to `REPRODUCED`, record the exact Codex version, model slug, OS, permission mode, project trust, fixture commit, transport used, exact requested `agent_type`, setup/cleanup, sanitized observations, evaluation, and hashes. Do not commit transcripts, credentials, private paths, proof values, session IDs, or unrelated repository data.
''',
    'fixture/README.md': '''# C13 fixture

The deterministic harness owns this synthetic fixture.

Ephemeral attempt:
- project-scoped agent file `.codex/agents/fixture_agent.toml`;
- declared agent name `fixture_agent`;
- spawn request with `agent_type` exactly `fixture_agent`;
- project-scoped `SubagentStart` hook matcher `^fixture_agent$`.

Recognized-error fallback only:
- separate disposable Git repository with the same project-scoped hook/config;
- no project-scoped `.codex/agents` child definition;
- synthetic child materialized only as `CODEX_HOME/agents/fixture_agent.toml` inside a disposable `CODEX_HOME`;
- spawn request still uses `agent_type` exactly `fixture_agent`;
- sandbox remains read-only and repository state must remain unchanged.
''',
    'fixture/agent-role.txt': '''Synthetic agent role: fixture_agent.
The real spawn request must set agent_type exactly to fixture_agent because Codex 0.152 uses agent_type as the SubagentStart matcher input. The ephemeral attempt is project-scoped. The recognized-error fallback materializes the same role only in disposable CODEX_HOME/agents while keeping SubagentStart hooks project-scoped.
''',
    'config/README.md': '''# C13 sandbox configuration — baseline 2.3

Use the deterministic live qualification harness rather than an interactive manual session.

Common requirements:

```toml
[agents]
enabled = true
max_concurrent_threads_per_session = 2
```

- model: `gpt-5.6-sol`;
- approval: `never`;
- sandbox: `read-only`;
- model-tool network: disabled;
- trusted disposable Git repository;
- real project-scoped `SubagentStart` hook;
- aligned agent filename/name/matcher: `fixture_agent.toml` / `fixture_agent` / `^fixture_agent$`;
- real spawn request uses `agent_type=fixture_agent`.

Transport is ephemeral-first. A non-ephemeral retry is allowed only for the recognized parent-thread registration failure. The retry uses a disposable `CODEX_HOME`, home-scoped synthetic agent, temporary file-backed auth symlink, isolated SQLite/log paths, `history.persistence="none"`, mandatory cleanup, and auth-metadata verification.
''',
    'prompt.txt': '''Capability qualification C13: real SubagentStart context semantics on Codex 0.152.

Start exactly one configured child through the real Codex `spawn_agent` mechanism with `agent_type` exactly `fixture_agent`. Do not omit agent_type, do not use a default/unnamed child, do not simulate the child, and do not invoke hook scripts manually. The root session must not use command/file mutation tools.

The real project-scoped SubagentStart hook injects an opaque proof that is not present in this prompt and returns `continue=false`. On Codex 0.152, continue=false is a compatibility signal for this event, not a stop control. Wait for the real child and preserve only the minimal structural result needed to establish whether it received and echoed the injected proof.

Do not expose credentials, proof values, usernames, home directories, session/thread IDs, private repository URLs, or full transcripts.
''',
    'run-command.txt': '''# Preferred controlled execution from main:
# Actions -> PlanAnvil Codex qualification -> mode=full
#
# Equivalent controller invocation inside the trusted disposable qualification workspace:
python3 tools/live_codex_qualification_harness_v6.py \\
  --root <QUALIFICATION_REPO> \\
  --source-commit <FULL_MAIN_SHA> \\
  --run-id <RUN_ID> \\
  --output <SANITIZED_ARTIFACT_DIR> \\
  --allow-c13-non-ephemeral-fallback
#
# The permission flag does not force non-ephemeral execution. C13 always runs
# ephemeral first and activates the fallback only for the recognized parent-thread failure.
''',
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

    # The stable archive remains the historical prepared-package source. Small
    # deterministic overlays keep runtime-sensitive release-gating capability
    # documentation synchronized with the current product/harness contract and
    # recompute package hashes before validation.
    written.extend(_apply_overlay(target_root, 'C06', C06_CODEX0152_OVERLAY))
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
