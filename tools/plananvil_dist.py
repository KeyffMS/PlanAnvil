from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

STATE_REL = Path('.plananvil/installation.json')
MANIFEST_REL = Path('distribution/manifest.json')
CONFIG_REL = Path('.codex/config.toml')
HOOKS_REL = Path('.codex/hooks.json')
BEGIN_CONFIG = '# BEGIN PLANANVIL MANAGED AGENT SETTINGS'
END_CONFIG = '# END PLANANVIL MANAGED AGENT SETTINGS'
HOOK_TOKEN = '.codex/hooks/plan-anvil-'


class DistError(RuntimeError):
    pass


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode('utf-8')


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f'.{path.name}.plananvil-tmp')
    tmp.write_bytes(data)
    os.replace(tmp, path)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise DistError(f'missing required file: {path}') from exc
    except json.JSONDecodeError as exc:
        raise DistError(f'invalid JSON in {path}: {exc}') from exc


def safe_rel(raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute() or not raw or any(part in {'', '.', '..'} for part in path.parts):
        raise DistError(f'unsafe relative path: {raw!r}')
    return path


def target_path(root: Path, rel: Path) -> Path:
    candidate = (root / rel).resolve(strict=False)
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise DistError(f'target path escapes repository: {rel}') from exc
    return candidate


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(['git', *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if check and result.returncode != 0:
        raise DistError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result


def git_root(path: Path) -> Path:
    return Path(git(path, 'rev-parse', '--show-toplevel').stdout.strip()).resolve()


def require_clean(root: Path, allow_dirty: bool) -> None:
    if allow_dirty:
        return
    if git(root, 'status', '--porcelain', '--untracked-files=all').stdout.strip():
        raise DistError('target repository is not clean; commit/stash changes or pass --allow-dirty')


def source_commit(source: Path) -> str | None:
    result = git(source, 'rev-parse', 'HEAD', check=False)
    value = result.stdout.strip()
    return value if result.returncode == 0 and re.fullmatch(r'[0-9a-f]{40,64}', value) else None


@dataclass
class Snapshot:
    existed: bool
    data: bytes | None


class Transaction:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.snapshots: dict[Path, Snapshot] = {}
        self.created_dirs: list[Path] = []

    def capture(self, path: Path) -> None:
        if path in self.snapshots:
            return
        cursor = path.parent
        missing: list[Path] = []
        while cursor != self.root and not cursor.exists():
            missing.append(cursor)
            cursor = cursor.parent
        for directory in reversed(missing):
            if directory not in self.created_dirs:
                self.created_dirs.append(directory)
        if path.exists():
            if path.is_dir():
                raise DistError(f'expected file, found directory: {path}')
            self.snapshots[path] = Snapshot(True, path.read_bytes())
        else:
            self.snapshots[path] = Snapshot(False, None)

    def rollback(self) -> None:
        for path, snap in reversed(list(self.snapshots.items())):
            try:
                if snap.existed:
                    write_bytes(path, snap.data or b'')
                elif path.exists():
                    path.unlink()
            except OSError:
                pass
        for directory in sorted(set(self.created_dirs), key=lambda item: len(item.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass


def load_manifest(source: Path) -> dict[str, Any]:
    value = load_json(source / MANIFEST_REL)
    if not isinstance(value, dict) or value.get('format_version') != 1:
        raise DistError('unsupported distribution manifest')
    version = value.get('product_version')
    if not isinstance(version, str) or not re.fullmatch(r'\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?', version):
        raise DistError('invalid product_version')
    roots = value.get('copy_roots')
    if not isinstance(roots, list) or not roots or not all(isinstance(item, str) for item in roots):
        raise DistError('copy_roots must be a non-empty string list')
    for raw in roots:
        safe_rel(raw)
    if not isinstance(value.get('hooks_source'), str):
        raise DistError('hooks_source is required')
    safe_rel(value['hooks_source'])
    return value


def iter_payload(source: Path, manifest: dict[str, Any]) -> Iterable[tuple[Path, Path]]:
    seen: set[Path] = set()
    for raw in manifest['copy_roots']:
        rel = safe_rel(raw)
        src = source / rel
        if not src.exists():
            raise DistError(f'distribution payload missing: {rel}')
        candidates = [src] if src.is_file() else sorted(p for p in src.rglob('*') if p.is_file())
        for path in candidates:
            if path.is_symlink():
                raise DistError(f'symlink is not allowed in payload: {path.relative_to(source)}')
            child = path.relative_to(source)
            if '__pycache__' in child.parts or path.suffix in {'.pyc', '.pyo'} or child in seen:
                continue
            seen.add(child)
            yield child, path


def desired_hooks(source: Path, manifest: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    value = load_json(source / safe_rel(manifest['hooks_source']))
    hooks = value.get('hooks') if isinstance(value, dict) else None
    if not isinstance(hooks, dict):
        raise DistError('hooks source must contain an object named hooks')
    result: dict[str, list[dict[str, Any]]] = {}
    for event, entries in hooks.items():
        if not isinstance(event, str) or not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
            raise DistError('invalid hooks source structure')
        if any(HOOK_TOKEN not in json.dumps(entry, sort_keys=True) for entry in entries):
            raise DistError(f'non-PlanAnvil entry found in hooks source: {event}')
        result[event] = entries
    return result


def load_target_hooks(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {'hooks': {}}
    value = load_json(path)
    if not isinstance(value, dict) or not isinstance(value.get('hooks', {}), dict):
        raise DistError('.codex/hooks.json must contain a hooks object')
    value.setdefault('hooks', {})
    for event, entries in value['hooks'].items():
        if not isinstance(event, str) or not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
            raise DistError('.codex/hooks.json has invalid entries')
    return value


def merge_hooks(target: dict[str, Any], desired: dict[str, list[dict[str, Any]]], previous: dict[str, list[dict[str, Any]]] | None = None) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    previous = previous or {}
    hooks = target['hooks']
    managed: dict[str, list[dict[str, Any]]] = {}
    for event, wanted in desired.items():
        current = hooks.setdefault(event, [])
        for old in previous.get(event, []):
            if old in current and old not in wanted:
                current.remove(old)
        for entry in current:
            if HOOK_TOKEN in json.dumps(entry, sort_keys=True) and entry not in wanted:
                raise DistError(f'conflicting unmanaged PlanAnvil hook for {event}')
        for entry in wanted:
            if entry not in current:
                current.append(entry)
        managed[event] = list(wanted)
    return target, managed


SECTION_RE = re.compile(r'^\s*\[([^\]]+)\]\s*(?:#.*)?$')


def find_section(lines: list[str], section: str) -> tuple[int, int] | None:
    start = None
    for idx, line in enumerate(lines):
        match = SECTION_RE.match(line)
        if not match:
            continue
        name = match.group(1).strip()
        if start is None and name == section:
            start = idx
        elif start is not None:
            return start, idx
    return (start, len(lines)) if start is not None else None


def section_key(lines: list[str], start: int, end: int, key: str) -> str | None:
    pattern = re.compile(rf'^\s*{re.escape(key)}\s*=\s*(.*?)\s*(?:#.*)?$')
    for idx in range(start + 1, end):
        match = pattern.match(lines[idx])
        if match:
            return match.group(1).strip()
    return None


def strip_managed_block(text: str, expected: str | None = None) -> str:
    if BEGIN_CONFIG not in text and END_CONFIG not in text:
        return text
    if expected is not None and expected not in text:
        raise DistError('managed .codex/config.toml block was modified')
    pattern = re.compile(rf'(?:\n)?{re.escape(BEGIN_CONFIG)}\n.*?{re.escape(END_CONFIG)}\n?', re.DOTALL)
    updated, count = pattern.subn('\n', text, count=1)
    if count != 1:
        raise DistError('invalid PlanAnvil managed config block')
    return updated.lstrip('\n') if not updated.strip() else updated


def plan_config(current: str, desired: dict[str, Any], previous_block: str | None = None) -> tuple[str, str | None]:
    base = strip_managed_block(current, previous_block) if previous_block else current
    lines = base.splitlines()
    section = find_section(lines, 'agents')
    enabled_wanted = bool(desired.get('enabled', True))
    threads_wanted = int(desired.get('max_concurrent_threads_per_session', 4))
    if threads_wanted < 1:
        raise DistError('desired agent concurrency must be positive')

    if section is None:
        block = (f'{BEGIN_CONFIG}\n[agents]\n'
                 f"enabled = {'true' if enabled_wanted else 'false'}\n"
                 f'max_concurrent_threads_per_session = {threads_wanted}\n{END_CONFIG}\n')
        text = base
        if text and not text.endswith('\n'):
            text += '\n'
        if text.strip():
            text += '\n'
        return text + block, block

    start, end = section
    missing: list[str] = []
    enabled = section_key(lines, start, end, 'enabled')
    if enabled is None:
        missing.append(f"enabled = {'true' if enabled_wanted else 'false'}")
    elif enabled.lower() not in {'true', 'false'} or (enabled.lower() == 'true') != enabled_wanted:
        raise DistError('existing [agents].enabled conflicts with PlanAnvil')

    threads = section_key(lines, start, end, 'max_concurrent_threads_per_session')
    legacy = section_key(lines, start, end, 'max_threads')
    value = threads if threads is not None else legacy
    if value is None:
        missing.append(f'max_concurrent_threads_per_session = {threads_wanted}')
    else:
        try:
            if int(value) < 1:
                raise ValueError
        except ValueError as exc:
            raise DistError('existing agent concurrency is not a positive integer') from exc

    if not missing:
        return base, None
    block = BEGIN_CONFIG + '\n' + '\n'.join(missing) + '\n' + END_CONFIG + '\n'
    insertion = start + 1
    new_lines = lines[:insertion] + [BEGIN_CONFIG, *missing, END_CONFIG] + lines[insertion:]
    return '\n'.join(new_lines) + '\n', block


def read_state(root: Path) -> dict[str, Any] | None:
    path = root / STATE_REL
    if not path.exists():
        return None
    value = load_json(path)
    if not isinstance(value, dict) or value.get('format_version') != 1:
        raise DistError('unsupported installation state')
    return value


def plan_payload(source: Path, root: Path, manifest: dict[str, Any], previous: dict[str, Any] | None) -> tuple[list[tuple[Path, Path, str, bool]], dict[str, dict[str, Any]]]:
    previous_files = previous.get('files', {}) if previous else {}
    plan: list[tuple[Path, Path, str, bool]] = []
    state_files: dict[str, dict[str, Any]] = {}
    for rel, src in iter_payload(source, manifest):
        dest = target_path(root, rel)
        digest = sha256_file(src)
        old = previous_files.get(rel.as_posix())
        owned = True
        if dest.exists():
            if dest.is_dir():
                raise DistError(f'payload destination is a directory: {rel}')
            current = sha256_file(dest)
            if old:
                if old.get('owned') and current != old.get('sha256'):
                    raise DistError(f'managed file was modified locally: {rel}')
                if not old.get('owned'):
                    if current != digest:
                        raise DistError(f'adopted file conflicts with upgrade payload: {rel}')
                    owned = False
            elif current == digest:
                owned = False
            else:
                raise DistError(f'target contains a conflicting file: {rel}')
        plan.append((rel, src, digest, owned))
        state_files[rel.as_posix()] = {'sha256': digest, 'owned': owned}
    return plan, state_files


def install_or_upgrade(source: Path, target: Path, upgrade: bool, allow_dirty: bool) -> dict[str, Any]:
    source = source.resolve()
    root = git_root(target.resolve())
    require_clean(root, allow_dirty)
    manifest = load_manifest(source)
    previous = read_state(root)
    if upgrade and previous is None:
        raise DistError('PlanAnvil is not installed; run install first')
    if not upgrade and previous is not None:
        raise DistError('PlanAnvil is already installed; run upgrade instead')

    payload, state_files = plan_payload(source, root, manifest, previous)
    config_path = root / CONFIG_REL
    current_config = config_path.read_text(encoding='utf-8') if config_path.exists() else ''
    old_block = previous.get('config', {}).get('managed_block') if previous else None
    config_text, block = plan_config(current_config, manifest.get('agents_config', {}), old_block)
    hooks_path = root / HOOKS_REL
    hooks, managed_hooks = merge_hooks(
        load_target_hooks(hooks_path), desired_hooks(source, manifest),
        previous.get('hooks', {}).get('entries', {}) if previous else None,
    )
    state = {
        'format_version': 1,
        'product_version': manifest['product_version'],
        'source_commit': source_commit(source),
        'installed_at': previous.get('installed_at') if previous else utcnow(),
        'updated_at': utcnow(),
        'files': state_files,
        'config': {'managed_block': block, 'file_created_by_plananvil': not config_path.exists()},
        'hooks': {'entries': managed_hooks, 'file_created_by_plananvil': not hooks_path.exists()},
    }
    tx = Transaction(root)
    state_path = root / STATE_REL
    try:
        for rel, src, _digest, owned in payload:
            dest = target_path(root, rel)
            if not owned and dest.exists():
                continue
            tx.capture(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        if config_text != current_config:
            tx.capture(config_path)
            write_bytes(config_path, config_text.encode('utf-8'))
        hooks_data = json_bytes(hooks)
        if not hooks_path.exists() or hooks_path.read_bytes() != hooks_data:
            tx.capture(hooks_path)
            write_bytes(hooks_path, hooks_data)
        tx.capture(state_path)
        write_bytes(state_path, json_bytes(state))
    except Exception:
        tx.rollback()
        raise
    return state


def verify_installation(target: Path) -> dict[str, Any]:
    root = git_root(target.resolve())
    state = read_state(root)
    if state is None:
        raise DistError('PlanAnvil is not installed')
    problems: list[str] = []
    for raw, entry in state.get('files', {}).items():
        path = target_path(root, safe_rel(raw))
        if not path.is_file():
            problems.append(f'missing file: {raw}')
        elif sha256_file(path) != entry.get('sha256'):
            problems.append(f'hash mismatch: {raw}')
    block = state.get('config', {}).get('managed_block')
    if block:
        path = root / CONFIG_REL
        if not path.exists() or block not in path.read_text(encoding='utf-8'):
            problems.append('managed .codex/config.toml block missing or changed')
    entries = state.get('hooks', {}).get('entries', {})
    if entries:
        path = root / HOOKS_REL
        if not path.exists():
            problems.append('.codex/hooks.json missing')
        else:
            hooks = load_target_hooks(path)['hooks']
            for event, managed in entries.items():
                for entry in managed:
                    if entry not in hooks.get(event, []):
                        problems.append(f'managed hook missing: {event}')
    return {'ok': not problems, 'product_version': state.get('product_version'), 'problems': problems}


def preflight_uninstall(root: Path, state: dict[str, Any]) -> None:
    for raw, entry in state.get('files', {}).items():
        if not entry.get('owned'):
            continue
        path = target_path(root, safe_rel(raw))
        if path.exists() and (path.is_dir() or sha256_file(path) != entry.get('sha256')):
            raise DistError(f'managed file was modified locally; refusing to remove: {raw}')
    block = state.get('config', {}).get('managed_block')
    path = root / CONFIG_REL
    if block and path.exists() and block not in path.read_text(encoding='utf-8'):
        raise DistError('managed .codex/config.toml block was modified')
    hook_entries = state.get('hooks', {}).get('entries', {})
    hook_path = root / HOOKS_REL
    if hook_entries and hook_path.exists():
        current_hooks = load_target_hooks(hook_path)['hooks']
        for event, managed in hook_entries.items():
            for entry in managed:
                if entry not in current_hooks.get(event, []) and any(
                    HOOK_TOKEN in json.dumps(candidate, sort_keys=True)
                    for candidate in current_hooks.get(event, [])
                ):
                    raise DistError(f'managed hook for {event} was modified')


def uninstall(target: Path, allow_dirty: bool) -> dict[str, Any]:
    root = git_root(target.resolve())
    require_clean(root, allow_dirty)
    state = read_state(root)
    if state is None:
        raise DistError('PlanAnvil is not installed')
    preflight_uninstall(root, state)
    tx = Transaction(root)
    removed: list[str] = []
    state_path = root / STATE_REL
    config_path = root / CONFIG_REL
    hooks_path = root / HOOKS_REL
    try:
        for raw, entry in state.get('files', {}).items():
            if not entry.get('owned'):
                continue
            path = target_path(root, safe_rel(raw))
            if path.exists():
                tx.capture(path)
                path.unlink()
                removed.append(raw)
        block = state.get('config', {}).get('managed_block')
        if block and config_path.exists():
            tx.capture(config_path)
            updated = strip_managed_block(config_path.read_text(encoding='utf-8'), block)
            if updated.strip():
                write_bytes(config_path, updated.encode('utf-8'))
            else:
                config_path.unlink()
        entries = state.get('hooks', {}).get('entries', {})
        if entries and hooks_path.exists():
            tx.capture(hooks_path)
            value = load_target_hooks(hooks_path)
            for event, managed in entries.items():
                current = value['hooks'].get(event, [])
                for entry in managed:
                    if entry in current:
                        current.remove(entry)
                if not current:
                    value['hooks'].pop(event, None)
            if value['hooks'] or any(key != 'hooks' for key in value):
                write_bytes(hooks_path, json_bytes(value))
            else:
                hooks_path.unlink()
        tx.capture(state_path)
        state_path.unlink()
    except Exception:
        tx.rollback()
        raise
    for directory in sorted({(root / safe_rel(raw)).parent for raw in removed} | {state_path.parent}, key=lambda p: len(p.parts), reverse=True):
        current = directory
        while current != root:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent
    return {'ok': True, 'removed_files': sorted(removed)}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='PlanAnvil repository distribution manager')
    p.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('install', 'upgrade', 'uninstall'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--target', type=Path, default=Path.cwd())
        cmd.add_argument('--allow-dirty', action='store_true')
    for name in ('verify', 'status'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--target', type=Path, default=Path.cwd())
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == 'install':
            result = install_or_upgrade(args.source, args.target, False, args.allow_dirty)
        elif args.command == 'upgrade':
            result = install_or_upgrade(args.source, args.target, True, args.allow_dirty)
        elif args.command == 'uninstall':
            result = uninstall(args.target, args.allow_dirty)
        elif args.command == 'verify':
            result = verify_installation(args.target)
            if not result['ok']:
                print(json.dumps(result, indent=2, sort_keys=True))
                return 2
        elif args.command == 'status':
            root = git_root(args.target.resolve())
            state = read_state(root)
            result = {'installed': state is not None, 'state': state}
        else:
            raise AssertionError(args.command)
    except DistError as exc:
        print(f'PlanAnvil distribution error: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
