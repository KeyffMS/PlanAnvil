from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import qualification_c08 as c08
import qualification_process as process
import live_codex_qualification_harness_v7 as v7
from test_qualification_execution_boundaries import execute_hook

v4 = v7.compat.v4
base = v4.base


def payload():
    return {'capability_id': 'C08', 'trial': c08.REPAIRED_TRIAL, 'outcome': 'PASS',
            'assertions': [], 'observations': ['C08_FINISHED'], 'blocker': None}


def events(repaired=True):
    phases = c08.PHASES if repaired else ('pressure',)
    return {'process_cleanup_ok': True, 'process_returncode': 0 if repaired else 1, 'timeout': False,
            'completed_command_items': len(phases), 'event_types': {'turn.completed': 1} if repaired else {},
            'event_tail': [{'event': 'item.completed', 'item': 'command_execution', 'command': 'c08_' + phase,
                            'exit_code': 0, 'c08_receipt_ok': True, 'c08_checkpoint_ok': repaired} for phase in phases]}


def records(repaired=True):
    rows = [{'event': 'PreToolUse', 'c08_phase': 'pressure', 'returncode': 0},
            {'event': 'PreCompact', 'trigger': 'auto', 'returncode': 0}]
    if repaired:
        rows += [{'event': 'PostCompact', 'trigger': 'auto', 'returncode': 0},
                 {'event': 'SessionStart', 'source': 'compact', 'additional_context': True, 'returncode': 0},
                 {'event': 'PreToolUse', 'c08_phase': 'finish', 'returncode': 0}]
    else:
        rows[-1].update({'continue': False, 'stop_reason_mentions_checkpoint': True})
    return rows


class C08ProtocolTests(unittest.TestCase):
    def test_complete_stop_and_positive_completion(self):
        for repaired in (False, True):
            self.assertTrue(all(c08.protocol_checks(events(repaired), records(repaired), repaired=repaired).values()))

    def test_timeout_or_broken_diagnostics_cannot_pass_even_after_compaction(self):
        for repaired in (False, True):
            for key, value in [('timeout', True), ('reader_failed', True), ('process_cleanup_ok', False),
                               ('oversized_lines', 1), ('invalid_json_lines', 1), ('event_tail_truncated', True),
                               ('process_returncode', None)]:
                data = events(repaired); data[key] = value
                self.assertFalse(all(c08.protocol_checks(data, records(repaired), repaired=repaired).values()))

    def test_missing_repeated_failed_commands_and_fake_receipts_fail(self):
        for mutation in ('missing', 'repeat', 'exit', 'receipt', 'checkpoint', 'count'):
            data = events()
            if mutation == 'missing': data['event_tail'].pop()
            elif mutation == 'repeat': data['event_tail'].append(data['event_tail'][0])
            elif mutation == 'exit': data['event_tail'][1]['exit_code'] = 2
            elif mutation == 'receipt': data['event_tail'][1]['c08_receipt_ok'] = False
            elif mutation == 'checkpoint': data['event_tail'][1]['c08_checkpoint_ok'] = False
            else: data['completed_command_items'] = 3
            self.assertFalse(all(c08.protocol_checks(data, records(), repaired=True).values()))

    def test_wrong_lifecycle_manual_compaction_failed_hook_and_missing_context_fail(self):
        for mode in ('missing', 'repeat', 'manual', 'exit', 'context', 'startup', 'stop'):
            rows = records()
            if mode == 'missing': rows.pop(2)
            elif mode == 'repeat': rows.append(rows[0])
            elif mode == 'manual': rows[1]['trigger'] = 'manual'
            elif mode == 'exit': rows[2]['returncode'] = 2
            elif mode == 'context': rows[3]['additional_context'] = False
            elif mode == 'startup': rows[3]['source'] = 'startup'
            else: rows[1]['continue'] = False
            self.assertFalse(all(c08.protocol_checks(events(), rows, repaired=True).values()))

    def test_negative_requires_checkpoint_stop_and_must_not_complete(self):
        rows = records(False); rows[-1]['stop_reason_mentions_checkpoint'] = False
        self.assertFalse(all(c08.protocol_checks(events(False), rows, repaired=False).values()))
        data = events(False); data['event_types']['turn.completed'] = 1
        self.assertFalse(all(c08.protocol_checks(data, records(False), repaired=False).values()))

    def test_adapter_retains_finite_limit_and_other_capabilities(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = v4.C09_COMPACT_LIMIT
            with v7.compat._codex0152_compaction(Path(tmp), 'C08'):
                self.assertEqual(v4.C08_COMPACT_LIMIT, 8192)
                self.assertEqual(v4.C09_COMPACT_LIMIT, old)

    def test_command_receipt_observation_is_content_free(self):
        collector = process.StructuralEvents()
        cmd = c08.COMMANDS['pressure']
        self.assertEqual(process.command_label('/bin/bash -lc "' + cmd + '"'), 'c08_pressure')
        self.assertEqual(process.command_label(cmd + '; echo secret'), 'other')
        collector.accept(json.dumps({'type': 'item.completed', 'item': {'type': 'command_execution',
            'command': cmd, 'exit_code': 0, 'aggregated_output': 'PRIVATE_CONTENT\n' + json.dumps({
                'c08_phase': 'pressure', 'canonical_read': True, 'checkpoint_ok': False, 'git_reconciled': False})}}).encode())
        summary = collector.summary()
        self.assertTrue(summary['event_tail'][0]['c08_receipt_ok'])
        self.assertIs(summary['event_tail'][0]['c08_checkpoint_ok'], False)
        self.assertNotIn('PRIVATE_CONTENT', json.dumps(summary))


class C08FixtureTests(unittest.TestCase):
    def test_actual_installer_same_run_repair_readonly_probes_and_product_hooks(self):
        """Model process substituted; product/checkpoint/Git/hook processes are real."""
        with tempfile.TemporaryDirectory(prefix='c08 fixture ') as tmp:
            rt = Path(tmp)
            calls = []
            planning_roots = []
            def drive(args, *, cwd, timeout):
                repaired = bool(calls)
                calls.append(repaired); planning_roots.append(cwd)
                self.assertIn('model_auto_compact_token_limit=8192', args)
                self.assertEqual(timeout, 600)
                self.assertEqual(args[args.index('--sandbox') + 1], 'read-only')
                primary = Path(base.git(cwd, 'rev-parse', '--path-format=absolute', '--git-common-dir')).parent
                configured = base.load_json(primary / '.codex/hooks.json')['hooks']
                self.assertTrue(all(g['matcher'] == '^compact$' for g in configured['SessionStart']))
                observed = process.StructuralEvents()
                def hook(name, phase=None):
                    event = {'hook_event_name': name, 'cwd': str(cwd), 'source': 'compact', 'trigger': 'auto'}
                    tag = 'compact' if name == 'SessionStart' else 'auto'
                    if phase:
                        tag = 'Bash'; event.update(tool_name='Bash', tool_input={'command': c08.COMMANDS[phase]})
                    result_payload = {}
                    for group in configured.get(name, []):
                        if group.get('matcher') and not re.search(group['matcher'], tag): continue
                        for h in group['hooks']:
                            result = execute_hook(h['command'], cwd, event)
                            self.assertEqual(result.returncode, 0, result.stderr)
                            result_payload = json.loads(result.stdout) if result.stdout.strip() else {}
                    return result_payload
                for phase in (c08.PHASES if repaired else ('pressure',)):
                    hook('PreToolUse', phase)
                    result = subprocess.run([sys.executable, '-B', c08.SCRIPT, phase], cwd=cwd,
                                            capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertNotIn(str(cwd), result.stdout)
                    observed.accept(json.dumps({'type': 'item.completed', 'item': {'type': 'command_execution',
                        'command': c08.COMMANDS[phase], 'exit_code': 0, 'aggregated_output': result.stdout}}).encode())
                    if phase == 'pressure':
                        pre = hook('PreCompact')
                        if repaired:
                            self.assertIsNot(pre.get('continue'), False)
                            hook('PostCompact')
                            context = hook('SessionStart')['hookSpecificOutput']['additionalContext']
                            self.assertIn('C08_FINITE_RECOVERY', context)
                            self.assertNotIn('MAP_INSTRUCTIONS', context)
                        else:
                            self.assertIs(pre.get('continue'), False)
                if repaired:
                    observed.accept(b'{"type":"turn.completed"}')
                    base.json_dump(Path(args[args.index('-o') + 1]), payload())
                data = observed.summary()
                data.update(process_cleanup_ok=True, process_returncode=0 if repaired else 1, timeout=False)
                return process.ProcessResult(0 if repaired else 1, False, data)
            with mock.patch.dict(os.environ, {'CODEX_HOME': str(rt/'home')}), mock.patch.object(
                process, 'run_observed', side_effect=drive), mock.patch.object(v4, '_write_result',
                side_effect=lambda **kw: (kw['result'], True)) as writer:
                result, _ = v7.run_c08(root=ROOT, runtime_root=rt, schemas=base.write_schemas(rt/'schemas'),
                    version='codex-cli 0.153.4', os_name='offline', source_commit='b'*40, date='2026-09-07')
            self.assertEqual(result, 'REPRODUCED', writer.call_args.kwargs)
            self.assertEqual(calls, [False, True])
            self.assertEqual(planning_roots[0], planning_roots[1])
            self.assertFalse((rt/'home/config.toml').exists())
            for trial in writer.call_args.kwargs['trials']:
                self.assertTrue(all(trial['protocol_checks'].values()))
