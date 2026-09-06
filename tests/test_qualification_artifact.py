from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import prepare_capabilities
import qualification_artifact as pack


class EvidenceArchiveTests(unittest.TestCase):
    @contextmanager
    def fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "evidence"
            prepare_capabilities.materialize(ROOT, root, force=True)
            (root / "qualification-summary.json").write_text(json.dumps({"scope": ["C09", "C10", "C13"], "release_gate_passed": False}))
            yield root, Path(tmp) / "package.zip"

    def test_deterministic_archive_contains_all_manifest_listed_hidden_files(self):
        with self.fixture() as (root, output):
            result = pack.build_archive(root, output)
            first = output.read_bytes()
            self.assertTrue(result["complete"])
            self.assertEqual(result["manifest_listed_hidden_files"], 3)
            with zipfile.ZipFile(output) as z:
                for cid in pack.CAPABILITIES:
                    hashes = json.loads(z.read(f"capabilities/{cid}/hashes.json"))["files"]
                    for path, digest in hashes.items():
                        self.assertEqual(hashlib.sha256(z.read(f"capabilities/{cid}/{path}")).hexdigest(), digest)
            pack.build_archive(root, output)
            self.assertEqual(output.read_bytes(), first)

    def test_missing_hidden_fixture_is_rejected_before_upload(self):
        with self.fixture() as (root, output):
            names = [p for p in pack.collect_files(root) if "/.agents/" in p]
            self.assertTrue(names)
            (root / names[0]).unlink()
            with self.assertRaises(pack.ArchiveError):
                pack.build_archive(root, output)
            self.assertFalse(output.exists())

    def test_unlisted_secret_cannot_enter_archive(self):
        with self.fixture() as (root, output):
            (root / ".env").write_text("private=DO_NOT_UPLOAD")
            with self.assertRaises(pack.ArchiveError):
                pack.build_archive(root, output)
            self.assertFalse(output.exists())

    def test_archive_recheck_detects_missing_member_even_if_outer_manifest_is_rewritten(self):
        with self.fixture() as (root, output):
            pack.build_archive(root, output)
            with zipfile.ZipFile(output) as z:
                files = {name: z.read(name) for name in z.namelist()}
            hidden = next(name for name in files if "/.agents/" in name)
            files.pop(hidden)
            manifest = json.loads(files[pack.MANIFEST])
            del manifest["files"][hidden]
            files[pack.MANIFEST] = json.dumps(manifest).encode()
            with zipfile.ZipFile(output, "w") as z:
                for name, data in files.items():
                    z.writestr(name, data)
            with self.assertRaises(pack.ArchiveError):
                pack.verify_archive(output)

    def test_changed_data_cannot_replace_previous_good_archive(self):
        with self.fixture() as (root, output):
            pack.build_archive(root, output)
            previous = output.read_bytes()
            (root / "capabilities/C10/actual.sanitized.json").write_text("{}")
            with self.assertRaises(pack.ArchiveError):
                pack.build_archive(root, output)
            self.assertEqual(output.read_bytes(), previous)

    def test_unsafe_archive_member_is_rejected(self):
        with self.fixture() as (root, output):
            pack.build_archive(root, output)
            with zipfile.ZipFile(output, "a") as z:
                z.writestr("../not-evidence", "bad")
            with self.assertRaises(pack.ArchiveError):
                pack.verify_archive(output)

    def test_symlink_is_rejected_instead_of_reading_external_file(self):
        if os.name == "nt":
            self.skipTest("Windows symlink creation requires privileges not needed by the product")
        with self.fixture() as (root, output):
            external = root.parent / "external"
            external.write_text("private")
            (root / "unlisted-link").symlink_to(external)
            with self.assertRaises(pack.ArchiveError):
                pack.build_archive(root, output)

    def test_workflow_uploads_only_the_verified_archive(self):
        source = (ROOT / ".github/workflows/plananvil-codex-qualification.yml").read_text()
        self.assertIn('python3 tools/qualification_artifact.py', source)
        self.assertIn('path: ${{ env.QUALIFICATION_ARTIFACT }}.zip', source)
        self.assertNotIn('include-hidden-files: true', source)
        self.assertIn('test "${{ steps.package_evidence.outcome }}" = "success"', source)


if __name__ == "__main__":
    unittest.main()
