"""Actual CLI integration with a controlled peer, never live-model evidence."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest import mock
from test_qualification_c08 import ROOT, base, c08, payload, process, v4, v7
from test_qualification_c09_cli import request_kind


@unittest.skipUnless(os.environ.get('PLANANVIL_TEST_CODEX_BIN'), 'pinned CLI conformance job only')
class C08CLIConformance(unittest.TestCase):
    def test_actual_cli_stops_then_completes_repaired_same_run(self):
        binary = os.environ['PLANANVIL_TEST_CODEX_BIN']
        version = subprocess.check_output([binary, '--version'], text=True).strip()
        self.assertEqual(version, 'codex-cli 0.153.4')
        state = {'regular': 0, 'compact': 0, 'requests': 0, 'kinds': [], 'recovery': False}
        class Server(BaseHTTPRequestHandler):
            def log_message(self, *_args): pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                kind = request_kind(body); state['kinds'].append(kind); state['requests'] += 1
                if state['requests'] > 7:
                    self.send_error(400, 'Fixture request bound exceeded'); return
                if kind == 'compaction':
                    state['compact'] += 1
                    item = {'type': 'message', 'id': 'summary', 'role': 'assistant', 'content': [
                        {'type': 'output_text', 'text': 'Pressure completed; continue with finish only.'}]}
                    tokens = 32
                else:
                    index = state['regular']; state['regular'] += 1
                    if index == 2:
                        context = json.dumps(body['input'])
                        state['recovery'] = 'Recover PlanAnvil from files:' in context and 'C08_FINITE_RECOVERY' in context
                    if index < 3:
                        phase = 'pressure' if index < 2 else 'finish'
                        item = {'type': 'function_call', 'id': 'fc-'+str(index), 'call_id': 'call-'+str(index),
                                'name': 'exec_command', 'arguments': json.dumps({'cmd': c08.COMMANDS[phase],
                                    'max_output_tokens': c08.OUTPUT_TOKENS if phase == 'pressure' else 2048})}
                        tokens = 20000 if phase == 'pressure' else 8
                    else:
                        item = {'type': 'message', 'id': 'final', 'role': 'assistant',
                                'content': [{'type': 'output_text', 'text': json.dumps(payload())}]}
                        tokens = 64
                rid = 'c08-'+str(state['requests'])
                events = [{'type': 'response.created', 'response': {'id': rid}},
                          {'type': 'response.output_item.done', 'output_index': 0, 'item': item},
                          {'type': 'response.completed', 'response': {'id': rid, 'usage': {
                              'input_tokens': 1000, 'output_tokens': tokens, 'total_tokens': 1000+tokens}}}]
                data = ''.join('data: '+json.dumps(e)+'\n\n' for e in events).encode()
                self.send_response(200); self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
        with ThreadingHTTPServer(('127.0.0.1', 0), Server) as server, tempfile.TemporaryDirectory(prefix='c08 cli ') as tmp:
            rt = Path(tmp); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            original = base.common_codex_args; observed = process.run_observed
            def args(**kw):
                result = original(**kw); result[0] = binary
                result += ['-c', 'model_provider="fixture"', '-c', 'model_providers.fixture.name="Fixture"',
                           '-c', f'model_providers.fixture.base_url="http://127.0.0.1:{server.server_port}/v1"',
                           '-c', 'model_providers.fixture.wire_api="responses"',
                           '-c', 'model_providers.fixture.requires_openai_auth=false',
                           '-c', 'model_providers.fixture.stream_max_retries=0', '-c', 'model_providers.fixture.request_max_retries=0']
                return result
            def bound(args, **kw):
                kw['timeout'] = 120; return observed(args, **kw)
            try:
                with mock.patch.dict(os.environ, {'CODEX_HOME': str(rt/'home')}), mock.patch.object(
                    base, 'common_codex_args', side_effect=args), mock.patch.object(process, 'run_observed', side_effect=bound), mock.patch.object(
                    v4, '_write_result', side_effect=lambda **kw: (kw['result'], True)) as writer:
                    result, _ = v7.run_c08(root=ROOT, runtime_root=rt, schemas=base.write_schemas(rt/'schemas'),
                        version=version, os_name='offline-cli', source_commit='b'*40, date='2026-09-07')
                self.assertEqual(result, 'REPRODUCED', writer.call_args.kwargs)
                self.assertEqual(state['kinds'], ['turn', 'turn', 'compaction', 'turn', 'turn'], state)
                self.assertTrue(state['recovery'], state)
                print('C08_REAL_CLI_CONFORMANCE_OK: real negative stop, same-run checkpoint repair, finite positive completion')
            finally:
                server.shutdown(); thread.join(timeout=5)
