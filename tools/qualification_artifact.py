"""Package exactly the validated evidence, including manifest-listed dotfiles.

Only this archive is uploaded, never an expanded runner workspace. Verification
checks both the archive manifest and every capability's existing hashes.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import zipfile
from typing import Any

import validate_capabilities

CAPABILITIES = tuple(f"C{i:02d}" for i in range(1, 17))
TOP_FILES = {"qualification-summary.json", "capabilities/index.json", "capabilities/README.md"}
MANIFEST = "archive-manifest.json"
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024


class ArchiveError(ValueError):
    pass


def _safe_name(value: str) -> str:
    p = PurePosixPath(value)
    if (not value or p.is_absolute() or ".." in p.parts or "\\" in value
            or ":" in value or p.as_posix() != value or "\x00" in value):
        raise ArchiveError("Invalid evidence archive member name")
    return value


def _json(payload: bytes) -> dict[str, Any]:
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ArchiveError("Evidence manifest is not an object")
    return value


def _expected_files(payloads: dict[str, bytes]) -> set[str]:
    expected = set(TOP_FILES)
    index = _json(payloads["capabilities/index.json"])
    records = index.get("capabilities", [])
    if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
        raise ArchiveError("Invalid evidence index records")
    ids = [item.get("id") for item in records]
    if any(not isinstance(cid, str) for cid in ids) or sorted(ids) != list(CAPABILITIES):
        raise ArchiveError("Evidence index must contain C01-C16 exactly once")
    for cid in CAPABILITIES:
        prefix = f"capabilities/{cid}/"
        name = prefix + "hashes.json"
        expected.add(name)
        hashes = _json(payloads[name])
        if hashes.get("algorithm") != "sha256" or not isinstance(hashes.get("files"), dict):
            raise ArchiveError("Invalid capability hash manifest")
        for relative, digest in hashes["files"].items():
            member = prefix + _safe_name(relative)
            expected.add(member)
            if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise ArchiveError("Invalid capability digest")
            if member not in payloads or hashlib.sha256(payloads[member]).hexdigest() != digest:
                raise ArchiveError(f"Missing or changed evidence member: {member}")
    return expected


def collect_files(root: Path) -> dict[str, bytes]:
    root = root.resolve()
    payloads: dict[str, bytes] = {}
    total = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ArchiveError("Evidence archive must not contain symlinks")
        if not path.is_file():
            continue
        name = _safe_name(path.relative_to(root).as_posix())
        size = path.stat().st_size
        total += size
        if size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
            raise ArchiveError("Evidence exceeds archive size limits")
        payloads[name] = path.read_bytes()
    try:
        expected = _expected_files(payloads)
    except KeyError as exc:
        raise ArchiveError("Required evidence metadata is missing") from exc
    if set(payloads) != expected:
        raise ArchiveError("Evidence file set differs from the explicit capability manifests")
    errors = validate_capabilities.validate_all(root)
    if errors:
        raise ArchiveError("Capability validation failed before packaging: " + "; ".join(errors))
    return payloads


def verify_archive(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [_safe_name(info.filename) for info in infos]
        if len(names) != len(set(names)):
            raise ArchiveError("Duplicate archive member")
        if any(info.is_dir() or stat.S_ISLNK(info.external_attr >> 16) for info in infos):
            raise ArchiveError("Only regular evidence files are permitted")
        if any(info.file_size > MAX_FILE_BYTES for info in infos) or sum(x.file_size for x in infos) > MAX_TOTAL_BYTES:
            raise ArchiveError("Evidence exceeds archive size limits")
        payloads = {name: archive.read(name) for name in names}
    try:
        manifest = _json(payloads.pop(MANIFEST))
        expected = _expected_files(payloads)
    except KeyError as exc:
        raise ArchiveError("Required evidence metadata is missing from archive") from exc
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(payloads.items())}
    if set(payloads) != expected or manifest.get("files") != hashes or manifest.get("algorithm") != "sha256" or manifest.get("schema_version") != "1.0":
        raise ArchiveError("Archive manifest or complete evidence file set mismatch")
    return {"schema_version": "1.0", "complete": True, "file_count": len(payloads),
            "manifest_listed_hidden_files": sum(any(part.startswith(".") for part in PurePosixPath(name).parts) for name in payloads)}


def build_archive(root: Path, output: Path) -> dict[str, Any]:
    root, output = root.resolve(), output.resolve()
    if output == root or output.is_relative_to(root):
        raise ArchiveError("Archive output must be outside the staged evidence directory")
    payloads = collect_files(root)
    manifest = {"schema_version": "1.0", "algorithm": "sha256", "files": {
        name: hashlib.sha256(data).hexdigest() for name, data in sorted(payloads.items())}}
    payloads[MANIFEST] = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".evidence-", suffix=".zip", dir=output.parent)
    os.close(fd)
    tmp = Path(name)
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for relative, content in sorted(payloads.items()):
                info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, content)
        result = verify_archive(tmp)
        os.replace(tmp, output)
        return result
    finally:
        tmp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(build_archive(args.root, args.output), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
