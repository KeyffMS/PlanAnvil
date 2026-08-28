from __future__ import annotations

import tempfile
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import build_release
import prepare_capabilities
import release_check
import validate_capabilities


class ReleaseEngineeringTests(unittest.TestCase):
    def test_capability_templates_materialize_complete_hash_consistent_packages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prepared = Path(tmp) / 'prepared'
            prepare_capabilities.materialize(ROOT, prepared, force=True)
            self.assertEqual(validate_capabilities.validate_all(prepared), [])

    def test_candidate_release_metadata_passes_but_live_gate_remains_closed(self) -> None:
        candidate = release_check.release_blockers(ROOT, require_reproduced=False)
        self.assertEqual(candidate, [])
        strict = release_check.release_blockers(ROOT, require_reproduced=True)
        self.assertTrue(any('required capability' in item for item in strict), strict)

    def test_release_archive_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / 'first'
            second = Path(tmp) / 'second'
            a = build_release.build(ROOT, first)
            b = build_release.build(ROOT, second)
            self.assertEqual(Path(a['archive']).read_bytes(), Path(b['archive']).read_bytes())
            self.assertEqual(a['sha256'], b['sha256'])
            self.assertTrue((first / 'SHA256SUMS').is_file())
            self.assertTrue((first / 'release-notes.md').is_file())


if __name__ == '__main__':
    unittest.main()
