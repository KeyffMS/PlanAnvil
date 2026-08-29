from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REQUIRED_FILES = {
    'README.md',
    'prompt.txt',
    'run-command.txt',
    'expected.json',
    'actual.sanitized.json',
    'evaluation.json',
    'hashes.json',
}
VALID_RESULTS = {'NOT_RUN', 'REPRODUCED', 'FAILED', 'BLOCKED'}
SENSITIVE_PATTERNS = [
    re.compile(r'\b(?:sk|gh[pousr])_[A-Za-z0-9_-]{16,}\b'),
    re.compile(r'(?i)\b(?:password|api[_-]?key|access[_-]?token)\b\s*[:=]\s*["\']?[^\s"\']{8,}'),
    re.compile(r'(?<![A-Za-z0-9_.-])/(?:home|Users|private|var|tmp|opt|srv|mnt|Volumes)/[^\s`"\'<>]+'),
    re.compile(r'(?i)(?<![A-Za-z0-9])(?:[A-Z]:[\\/])[^\s`"\'<>]+'),
]


class CapabilityError(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise CapabilityError(f'{path}: invalid or unreadable JSON: {exc}') from exc


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package_files(directory: Path) -> list[Path]:
    result = []
    for path in directory.rglob('*'):
        if path.is_file() and path.name != 'hashes.json' and '__pycache__' not in path.parts:
            result.append(path)
    return sorted(result)


def _relative_set(paths: list[Path], root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in paths}


def validate_one(root: Path, capability_id: str, expected_index_result: str | None = None) -> list[str]:
    errors: list[str] = []
    directory = root / 'capabilities' / capability_id
    if not directory.is_dir():
        return [f'{capability_id}: evidence directory is missing']
    names = {path.name for path in directory.iterdir() if path.is_file()}
    missing = sorted(REQUIRED_FILES - names)
    if missing:
        errors.append(f'{capability_id}: missing files: {", ".join(missing)}')
    fixture = directory / 'fixture'
    config = directory / 'config'
    if not fixture.is_dir() or not any(path.is_file() for path in fixture.rglob('*')):
        errors.append(f'{capability_id}: fixture/ must contain at least one file')
    if not config.is_dir() or not any(path.is_file() for path in config.rglob('*')):
        errors.append(f'{capability_id}: config/ must contain at least one file')
    if errors:
        return errors

    expected = load_json(directory / 'expected.json')
    actual = load_json(directory / 'actual.sanitized.json')
    evaluation = load_json(directory / 'evaluation.json')
    hashes = load_json(directory / 'hashes.json')
    for label, value in [('expected', expected), ('actual', actual), ('evaluation', evaluation), ('hashes', hashes)]:
        if not isinstance(value, dict):
            errors.append(f'{capability_id}: {label}.json must contain an object')

    for label, value in [('expected', expected), ('actual', actual), ('evaluation', evaluation)]:
        if isinstance(value, dict) and value.get('capability_id') != capability_id:
            errors.append(f'{capability_id}: {label}.json capability_id mismatch')

    result = evaluation.get('result') if isinstance(evaluation, dict) else None
    if result not in VALID_RESULTS:
        errors.append(f'{capability_id}: evaluation result is invalid: {result!r}')
    if expected_index_result is not None and result != expected_index_result:
        errors.append(f'{capability_id}: index result {expected_index_result} != evaluation result {result}')
    if isinstance(actual, dict) and actual.get('result') != result:
        errors.append(f'{capability_id}: actual result does not match evaluation')

    if result == 'REPRODUCED':
        env = actual.get('environment') if isinstance(actual, dict) else None
        required_env = ('codex_version', 'model', 'os', 'permission_mode', 'project_trust')
        if not isinstance(env, dict) or any(not isinstance(env.get(key), str) or not env.get(key).strip() for key in required_env):
            errors.append(f'{capability_id}: REPRODUCED evidence lacks complete runtime metadata')
        if evaluation.get('expected_met') is not True:
            errors.append(f'{capability_id}: REPRODUCED evaluation must set expected_met=true')
        if actual.get('blocker'):
            errors.append(f'{capability_id}: REPRODUCED actual evidence cannot contain a blocker')
    elif result == 'BLOCKED':
        if not isinstance(actual.get('blocker'), str) or not actual.get('blocker').strip():
            errors.append(f'{capability_id}: BLOCKED actual evidence requires a blocker')

    text = (directory / 'actual.sanitized.json').read_text(encoding='utf-8')
    for pattern in SENSITIVE_PATTERNS:
        if pattern.search(text):
            errors.append(f'{capability_id}: actual.sanitized.json contains sensitive/private-looking data')
            break

    files = hashes.get('files') if isinstance(hashes, dict) else None
    if hashes.get('algorithm') != 'sha256' or not isinstance(files, dict):
        errors.append(f'{capability_id}: hashes.json must use sha256 and contain a files object')
    else:
        actual_files = package_files(directory)
        actual_set = _relative_set(actual_files, directory)
        hash_set = set(files)
        if actual_set != hash_set:
            errors.append(
                f'{capability_id}: hashes.json file set mismatch; missing={sorted(actual_set-hash_set)}, extra={sorted(hash_set-actual_set)}'
            )
        for path in actual_files:
            rel = path.relative_to(directory).as_posix()
            if files.get(rel) != sha256(path):
                errors.append(f'{capability_id}: hash mismatch for {rel}')
    return errors


def validate_all(root: Path) -> list[str]:
    index = load_json(root / 'capabilities/index.json')
    if not isinstance(index, dict) or not isinstance(index.get('capabilities'), list):
        return ['capabilities/index.json is invalid']
    errors: list[str] = []
    seen: set[str] = set()
    for item in index['capabilities']:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str):
            errors.append('capabilities/index.json contains an invalid capability record')
            continue
        capability_id = item['id']
        seen.add(capability_id)
        errors.extend(validate_one(root, capability_id, item.get('result')))
    expected_ids = {f'C{i:02d}' for i in range(1, 17)}
    if seen != expected_ids:
        errors.append(f'capability index IDs mismatch: expected {sorted(expected_ids)}, got {sorted(seen)}')
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Validate PlanAnvil capability evidence packages')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    errors = validate_all(args.root.resolve())
    if errors:
        for error in errors:
            print(f'ERROR: {error}', file=sys.stderr)
        return 2
    print('All PlanAnvil capability evidence packages are structurally valid and hash-consistent.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
