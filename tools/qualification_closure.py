"""Validate source-bound archived evidence; do not fabricate or promote results."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import zipfile

from qualification_artifact import verify_archive

C08_CHECKS = {'complete_process_observation', 'exact_completed_commands', 'ordered_automatic_lifecycle',
              'product_hook_decision', 'no_unexpected_tools', 'terminal_state', 'checkpoint_state',
              'source_and_planning_unchanged'}


def closure_blockers(root: Path) -> list[str]:
    errors = []
    try:
        index = json.loads((root / 'qualifications/index.json').read_text(encoding='utf-8'))
        run = index['current_run']
        if not isinstance(run, str) or not run.isascii() or not run.isdigit():
            raise ValueError('invalid current run identity')
        folder = root / 'qualifications' / run
        provenance = json.loads((folder / 'provenance.json').read_text(encoding='utf-8'))
        archive = folder / 'evidence-artifact.zip'
        if hashlib.sha256(archive.read_bytes()).hexdigest() != provenance['evidence_sha256']:
            raise ValueError('archived evidence hash mismatch')
        verify_archive(archive)
        with zipfile.ZipFile(archive) as z:
            summary = json.loads(z.read('qualification-summary.json'))
            if (summary['github_actions_run'] != run or summary['source_commit'] != provenance['source_commit']
                or summary.get('release_gate_passed') is not True
                or summary.get('results') != {f'C{i:02d}': 'REPRODUCED' for i in range(1, 17)}):
                raise ValueError('archive is not the complete qualified full run')
            # Each current package is the exact record from the referenced run.
            for name in z.namelist():
                if name.startswith('capabilities/C') and not name.endswith('/'):
                    if (root / name).read_bytes() != z.read(name):
                        raise ValueError('current capability differs from archived run: ' + name)
        product = json.loads((root / 'qualifications/product-files.json').read_text(encoding='utf-8'))
        current = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                   for directory in ('.agents', '.codex') for p in sorted((root / directory).rglob('*'))
                   if p.is_file() and '__pycache__' not in p.parts}
        if not current or current != product['files']:
            errors.append('product bytes changed since recorded live qualification')
        c08 = json.loads((root / 'capabilities/C08/actual.sanitized.json').read_text(encoding='utf-8'))
        trials = c08.get('trials', [])
        names = ['automatic_compaction_without_valid_checkpoint', 'automatic_compaction_after_checkpoint_repair']
        if len(trials) != 2 or [t.get('trial') for t in trials] != names:
            errors.append('C08 finite stop/repair trials are missing')
        else:
            for i, trial in enumerate(trials):
                required = C08_CHECKS | ({'completed_positive_output'} if i else set())
                checks = trial.get('protocol_checks', {})
                events = trial.get('event_summary', {})
                if (trial.get('protocol_version') != 'finite-c08-v1' or trial.get('outcome') != 'PASS'
                    or not required.issubset(checks) or any(checks[k] is not True for k in required)
                    or events.get('timeout') is not False or events.get('process_cleanup_ok') is not True
                    or events.get('process_returncode') != (0 if i else 1)):
                    errors.append('C08 requires committed finite live stop/repair completion evidence')
                    break
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        errors.append('qualification closure validation failed: ' + str(exc))
    return errors
