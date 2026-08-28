from __future__ import annotations

import argparse
import base64
import io
import shutil
import tarfile
from pathlib import Path, PurePosixPath

ARCHIVE = Path('capabilities/templates.tar.gz.b64')


def _safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != 'capabilities':
        raise ValueError(f'unsafe capability template path: {name}')
    return path


def materialize(source_root: Path, target_root: Path, *, force: bool = False) -> list[str]:
    source_root = source_root.resolve()
    target_root = target_root.resolve()
    raw = base64.b64decode((source_root / ARCHIVE).read_text(encoding='ascii'))
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
