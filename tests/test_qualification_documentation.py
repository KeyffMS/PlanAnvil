from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class QualificationDocumentationTests(unittest.TestCase):
    def setUp(self):
        self.index = json.loads((ROOT / 'qualifications/index.json').read_text(encoding='utf-8'))
        folder = ROOT / 'qualifications' / self.index['current_run']
        self.summary = json.loads((folder / 'qualification-summary.json').read_text(encoding='utf-8'))
        self.compliance = (ROOT / 'docs/OPENAI_COMPLIANCE.md').read_text(encoding='utf-8')

    def test_current_compliance_record_matches_archived_qualification(self):
        # Scope to the current record so preserved historical runs cannot satisfy it.
        section = self.compliance.split('### Current qualification\n', 1)[1]
        section = section.split('\n### ', 1)[0]
        rows = re.findall(r'^\| ([^|]+?) \| `([^`]+)` \|$', section, re.MULTILINE)
        self.assertEqual(len(rows), len(dict(rows)), 'duplicate qualification fields')
        self.assertEqual(dict(rows), {
            'Run': self.index['current_run'],
            'Source commit': self.summary['source_commit'],
            'Live date': self.summary['date'],
            'Codex': self.summary['codex_version'],
            'Model': self.summary['model'],
            'OS': self.summary['os'],
            'Full release gate': json.dumps(self.summary['release_gate_passed']),
            'Finite C08 closure': self.index['c08_closure'],
        })
        self.assertEqual(self.summary['github_actions_run'], self.index['current_run'])

    def test_finite_c08_checklist_matches_committed_closure(self):
        matches = re.findall(
            r'^- \[([ x])\] Finite C08 repaired-path completion verified live and committed for production closure$',
            self.compliance, re.MULTILINE,
        )
        self.assertEqual(len(matches), 1, 'finite C08 checklist must have one current entry')
        self.assertEqual(matches[0] == 'x', self.index['c08_closure'] == 'REPRODUCED')

    def test_current_version_notes_include_current_source_bound_result(self):
        version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
        changelog = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
        section = changelog.split(f'## [{version}]', 1)[1].split('\n## [', 1)[0]
        for value in (self.index['current_run'], self.summary['source_commit']):
            with self.subTest(value=value):
                self.assertIn(f'`{value}`', section)


if __name__ == '__main__':
    unittest.main()
