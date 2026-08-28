from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

EPOCH = (1980, 1, 1, 0, 0, 0)


def load_manifest(root: Path) -> dict:
    return json.loads((root / 'distribution/manifest.json').read_text(encoding='utf-8'))


def release_paths(root: Path, manifest: dict) -> list[Path]:
    result: set[Path] = set()
    for raw in manifest.get('release_files', []):
        path = root / raw
        if not path.is_file():
            raise RuntimeError(f'missing release file: {raw}')
        result.add(path)
    for raw in manifest.get('copy_roots', []):
        path = root / raw
        if path.is_file():
            result.add(path)
        elif path.is_dir():
            for child in path.rglob('*'):
                if child.is_file() and '__pycache__' not in child.parts and child.suffix not in {'.pyc', '.pyo'}:
                    result.add(child)
        else:
            raise RuntimeError(f'missing release payload: {raw}')
    hook_source = root / manifest['hooks_source']
    if not hook_source.is_file():
        raise RuntimeError('hooks source is missing')
    result.add(hook_source)
    return sorted(result, key=lambda p: p.relative_to(root).as_posix())


def changelog_notes(root: Path, version: str) -> str:
    text = (root / 'CHANGELOG.md').read_text(encoding='utf-8')
    marker = f'## [{version}]'
    start = text.find(marker)
    if start < 0:
        raise RuntimeError(f'CHANGELOG.md has no {version} section')
    next_start = text.find('\n## [', start + len(marker))
    section = text[start: next_start if next_start >= 0 else len(text)].strip()
    return f'# PlanAnvil {version}\n\n{section}\n'


def build(root: Path, output: Path) -> dict[str, str]:
    manifest = load_manifest(root)
    version = (root / 'VERSION').read_text(encoding='utf-8').strip()
    if manifest.get('product_version') != version:
        raise RuntimeError('manifest version does not match VERSION')
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f'plananvil-{version}.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in release_paths(root, manifest):
            rel = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(rel, date_time=EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zf.writestr(info, path.read_bytes())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    sums = output / 'SHA256SUMS'
    sums.write_text(f'{digest}  {archive.name}\n', encoding='utf-8')
    notes = output / 'release-notes.md'
    notes.write_text(changelog_notes(root, version), encoding='utf-8')
    return {'archive': str(archive), 'sha256': digest, 'checksums': str(sums), 'notes': str(notes)}


def main() -> int:
    parser = argparse.ArgumentParser(description='Build deterministic PlanAnvil release archive')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, default=Path('dist'))
    args = parser.parse_args()
    result = build(args.root.resolve(), args.output.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
