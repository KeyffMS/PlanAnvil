from __future__ import annotations

import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_production_release_rejects_dirty_tree(self) -> None:
        completed = type('Completed', (), {'returncode': 0, 'stdout': ' M README.md\n', 'stderr': ''})()
        with patch.object(release_check.subprocess, 'run', return_value=completed):
            blockers = release_check.release_blockers(ROOT, require_reproduced=True)
        self.assertIn(
            'release tree is dirty; commit or remove all tracked and untracked changes before production release',
            blockers,
        )

    def test_production_release_fails_closed_if_git_cleanliness_cannot_be_verified(self) -> None:
        completed = type('Completed', (), {'returncode': 128, 'stdout': '', 'stderr': 'not a git repository'})()
        with patch.object(release_check.subprocess, 'run', return_value=completed):
            blockers = release_check.release_blockers(ROOT, require_reproduced=True)
        self.assertIn('cannot verify clean release tree: not a git repository', blockers)

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
