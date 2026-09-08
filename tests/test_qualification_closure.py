"""Offline evidence-integrity tests; synthetic proofs never leave temp fixtures."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import prepare_capabilities as prepare
import qualification_closure as closure
import release_check
from qualification_artifact import build_archive, verify_archive


class ClosureTests(unittest.TestCase):
    def test_reviewed_current_full_archive_and_summary_are_consistent(self):
        # Verify archived evidence, not production eligibility of a development PR.
        # Current product binding remains the responsibility of release_check.py.
        index = json.loads((ROOT / 'qualifications/index.json').read_text())
        self.assertEqual(index['c08_closure'], 'REPRODUCED')
        folder = ROOT / 'qualifications' / index['current_run']
        provenance = json.loads((folder / 'provenance.json').read_text())
        self.assertEqual(provenance['qualification_mode'], 'full')
        verify_archive(folder / 'evidence-artifact.zip')
        with zipfile.ZipFile(folder / 'evidence-artifact.zip') as z:
            summary_bytes = z.read('qualification-summary.json')
            self.assertEqual((folder / 'qualification-summary.json').read_bytes(), summary_bytes)
            summary = json.loads(summary_bytes)
            self.assertEqual(summary['github_actions_run'], index['current_run'])
            self.assertEqual(summary['source_commit'], provenance['source_commit'])
            self.assertTrue(summary['release_gate_passed'])
            self.assertEqual(summary['required_not_reproduced'], [])

    def test_current_package_change_is_not_accepted_as_archived_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_repo(tmp)
            path = root / 'capabilities/C09/actual.sanitized.json'
            # Even a JSON-preserving edit is not the original source-bound record.
            with path.open('ab') as stream:
                stream.write(b'\n')
            self.assertTrue(any('current capability differs from archived run' in error
                                for error in closure.closure_blockers(root)))

    def copy_repo(self, tmp):
        target = Path(tmp)/'repo'
        shutil.copytree(ROOT, target, ignore=shutil.ignore_patterns('.git', '__pycache__'))
        return target

    def historical(self, root):
        # Always use original run25, regardless of the current released index.
        archive = root/'qualifications/34060321283/evidence-artifact.zip'
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                if name.startswith('capabilities/C'):
                    p=root/name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(z.read(name))
        (root/'qualifications/index.json').write_text(json.dumps({'current_run': '34060321283'}))

    def test_historical_timeout_is_not_rewritten_as_finite_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.copy_repo(tmp); self.historical(root)
            errors=closure.closure_blockers(root)
            self.assertIn('C08 requires committed finite live stop/repair completion evidence', errors)

    def test_product_change_is_rejected_independently_of_git_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.copy_repo(tmp)
            (root/'.agents/skills/plan-anvil/SKILL.md').write_text('changed')
            self.assertIn('product bytes changed since recorded live qualification', closure.closure_blockers(root))
            # Ordinary candidate PRs stay usable before new main-only live qualification.
            self.assertEqual(release_check.release_blockers(root, require_reproduced=False), [])

    def test_archive_digest_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.copy_repo(tmp)
            run=json.loads((root/'qualifications/index.json').read_text())['current_run']
            with (root/'qualifications'/run/'evidence-artifact.zip').open('ab') as f: f.write(b'changed')
            self.assertTrue(any('hash mismatch' in e for e in closure.closure_blockers(root)))

    def test_fresh_indices_are_reset_in_both_external_and_inplace_materialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=self.copy_repo(tmp)
            original=(source/'qualifications/34060321283/evidence-artifact.zip').read_bytes()
            for target in (Path(tmp)/'fresh', source):
                prepare.materialize(source, target, force=True)
                index=json.loads((target/'capabilities/index.json').read_text())
                self.assertTrue(all(i['result']=='BLOCKED' for i in index['capabilities']))
                self.assertEqual(index['qualification_attempt']['live_codex_result'], 'NOT_RUN')
                self.assertNotIn('github_actions_run', index['qualification_attempt'])
            self.assertEqual((source/'qualifications/34060321283/evidence-artifact.zip').read_bytes(), original)

    def test_c08_only_scope_never_promotes_full_gate(self):
        import live_codex_qualification_recovery as recovery
        result=recovery.selected_summary({'C08': 'REPRODUCED'}, ('C08',))
        self.assertTrue(result['selected_gate_passed'])
        self.assertFalse(result['release_gate_passed'])
        self.assertEqual(result['scope'], ['C08'])

    def test_consistent_synthetic_closed_archive_passes_only_in_temporary_fixture(self):
        from test_qualification_c08 import events, records
        with tempfile.TemporaryDirectory() as tmp:
            root=self.copy_repo(tmp); self.historical(root)
            folder=root/'qualifications/34060321283'
            evidence=Path(tmp)/'synthetic-evidence'
            with zipfile.ZipFile(folder/'evidence-artifact.zip') as z:
                z.extractall(evidence)
            (evidence/'archive-manifest.json').unlink()
            path=evidence/'capabilities/C08/actual.sanitized.json'
            actual=json.loads(path.read_text())
            for i, trial in enumerate(actual['trials']):
                trial.update(protocol_version='finite-c08-v1', outcome='PASS', blocker=None,
                    protocol_checks={k: True for k in closure.C08_CHECKS | ({'completed_positive_output'} if i else set())},
                    event_summary=events(bool(i)), hook_timeline=records(bool(i)))
            path.write_text(json.dumps(actual))
            prepare._rehash_capability(path.parent)
            shutil.copytree(path.parent, root/'capabilities/C08', dirs_exist_ok=True)
            build_archive(evidence, folder/'evidence-artifact.zip')
            provenance=json.loads((folder/'provenance.json').read_text())
            provenance['evidence_sha256']=hashlib.sha256((folder/'evidence-artifact.zip').read_bytes()).hexdigest()
            (folder/'provenance.json').write_text(json.dumps(provenance))
            self.assertEqual(closure.closure_blockers(root), [])
