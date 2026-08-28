from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rehash(directory: Path) -> None:
    files = {}
    for path in sorted(directory.rglob('*')):
        if path.is_file() and path.name != 'hashes.json' and '__pycache__' not in path.parts:
            files[path.relative_to(directory).as_posix()] = sha256(path)
    payload = {'schema_version': '1.0', 'algorithm': 'sha256', 'files': files}
    (directory / 'hashes.json').write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description='Recompute PlanAnvil capability evidence hashes')
    parser.add_argument('capability', nargs='?', help='C01..C16; omit with --all')
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    if args.all:
        ids = [f'C{i:02d}' for i in range(1, 17)]
    elif args.capability:
        ids = [args.capability.upper()]
    else:
        parser.error('provide a capability ID or --all')
    for cid in ids:
        directory = root / 'capabilities' / cid
        if not directory.is_dir():
            parser.error(f'missing capability directory: {cid}')
        rehash(directory)
        print(f'rehashed {cid}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
