from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from prepare_capabilities import materialize
from validate_capabilities import validate_all

SEMVER = re.compile(r'^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$')


def _git_clean_blocker(root: Path) -> str | None:
    result = subprocess.run(
        ['git', '-C', str(root), 'status', '--porcelain', '--untracked-files=all'],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or f'exit {result.returncode}'
        return f'cannot verify clean release tree: {detail}'
    if result.stdout.strip():
        return 'release tree is dirty; commit or remove all tracked and untracked changes before production release'
    return None


def release_blockers(root: Path, *, require_reproduced: bool = True, tag: str | None = None) -> list[str]:
    blockers: list[str] = []
    version_path = root / 'VERSION'
    if not version_path.is_file():
        return ['VERSION is missing']
    version = version_path.read_text(encoding='utf-8').strip()
    if not SEMVER.fullmatch(version):
        blockers.append(f'VERSION is not semver: {version!r}')

    manifest_path = root / 'distribution/manifest.json'
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        blockers.append(f'distribution manifest is invalid: {exc}')
        manifest = {}
    if manifest.get('product_version') != version:
        blockers.append('distribution manifest product_version does not match VERSION')

    changelog = (root / 'CHANGELOG.md').read_text(encoding='utf-8') if (root / 'CHANGELOG.md').is_file() else ''
    if f'## [{version}]' not in changelog:
        blockers.append(f'CHANGELOG.md has no section for {version}')

    if tag is not None and tag != f'v{version}':
        blockers.append(f'tag {tag!r} does not match VERSION v{version}')

    if require_reproduced:
        clean_blocker = _git_clean_blocker(root)
        if clean_blocker is not None:
            blockers.append(clean_blocker)
        blockers.extend(validate_all(root))
    else:
        try:
            with tempfile.TemporaryDirectory() as tmp:
                prepared = Path(tmp) / 'prepared'
                materialize(root, prepared, force=True)
                blockers.extend(validate_all(prepared))
        except Exception as exc:
            blockers.append(f'capability template materialization failed: {exc}')

    try:
        index = json.loads((root / 'capabilities/index.json').read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        blockers.append(f'capabilities/index.json is invalid: {exc}')
        index = {}
    if require_reproduced:
        for item in index.get('capabilities', []):
            if item.get('required') and item.get('result') != 'REPRODUCED':
                blockers.append(f"{item.get('id')}: required capability is {item.get('result')}, not REPRODUCED")

    required_release_files = manifest.get('release_files', []) if isinstance(manifest, dict) else []
    for raw in required_release_files:
        path = root / raw
        if not path.is_file():
            blockers.append(f'release file is missing: {raw}')
    return blockers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Validate PlanAnvil release readiness')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--candidate', action='store_true', help='validate candidate structure without requiring live REPRODUCED evidence')
    parser.add_argument('--tag')
    args = parser.parse_args(argv)
    blockers = release_blockers(args.root.resolve(), require_reproduced=not args.candidate, tag=args.tag)
    if blockers:
        for blocker in blockers:
            print(f'BLOCKER: {blocker}', file=sys.stderr)
        return 2
    mode = 'candidate' if args.candidate else 'release'
    print(f'PlanAnvil {mode} checks passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
