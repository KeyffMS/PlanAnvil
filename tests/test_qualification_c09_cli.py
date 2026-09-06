"""Real pinned Codex CLI against a loopback Responses simulator, no model service.

Opt-in hosted CI conformance check. It is not live C09 qualification evidence:
the simulator chooses tool calls and token usage. Codex itself must perform the
tools, compaction, product hooks, context injection and structured completion.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import live_codex_qualification_harness_v7 as v7
import qualification_c09 as c09
import qualification_process as process
from test_qualification_c09 import completed_payload


def request_kind(body):
    """Use pinned Codex request metadata, never the optional tools field.

    Source: rust-v0.153.4/core/src/responses_metadata.rs. Responses Lite may
    omit tools on ordinary turns; absence of tools is not a compaction signal.
    """
    metadata = body.get("client_metadata") or {}
    encoded = metadata.get("x-codex-turn-metadata")
    canonical = json.loads(encoded) if isinstance(encoded, str) else {}
    kind = canonical.get("request_kind", metadata.get("request_kind"))
    if kind not in {"turn", "compaction"}:
        raise ValueError("Missing or unexpected Codex request kind")
    if metadata.get("request_kind", kind) != kind:
        raise ValueError("Conflicting Codex request kind metadata")
    return kind


class RequestKindTests(unittest.TestCase):
    def test_turn_without_tools_is_not_compaction(self):
        body = {"client_metadata": {"x-codex-turn-metadata": json.dumps({"request_kind": "turn"})}}
        self.assertEqual(request_kind(body), "turn")
        body["tools"] = []
        self.assertEqual(request_kind(body), "turn")

    def test_compaction_is_identified_from_canonical_metadata(self):
        self.assertEqual(request_kind({"client_metadata": {"request_kind": "compaction"}}), "compaction")

    def test_missing_or_conflicting_metadata_is_rejected(self):
        for body in ({"tools": []}, {"client_metadata": {"request_kind": "turn",
                      "x-codex-turn-metadata": json.dumps({"request_kind": "compaction"})}}):
            with self.assertRaises(ValueError):
                request_kind(body)


@unittest.skipUnless(os.environ.get("PLANANVIL_TEST_CODEX_BIN"), "pinned CLI conformance job only")
class C09RealCLIConformance(unittest.TestCase):
    def test_actual_cli_finishes_two_compactions_and_recovery_in_one_turn(self):
        binary = os.environ["PLANANVIL_TEST_CODEX_BIN"]
        version = subprocess.check_output([binary, "--version"], text=True).strip()
        self.assertEqual(version, "codex-cli 0.153.4")
        state = {"regular": 0, "compact": 0, "context_seen": [], "requests": 0, "request_kinds": []}

        class Server(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                try:
                    body = json.loads(data)
                except ValueError:
                    self.send_error(400, "Expected uncompressed fixture JSON")
                    return
                state["requests"] += 1
                if state["requests"] > 10:
                    self.send_error(400, "Finite fixture request limit exceeded")
                    return
                try:
                    kind = request_kind(body)
                except ValueError:
                    state["metadata_error"] = True
                    self.send_error(400, "Missing or conflicting Codex request metadata")
                    return
                state["request_kinds"].append(kind)
                compact = kind == "compaction"
                if compact:
                    state["compact"] += 1
                    item = {"type": "message", "role": "assistant", "id": "summary-" + str(state["compact"]),
                            "content": [{"type": "output_text", "text": "Completed earlier C09 phase. Continue with next phase, do not repeat."}]}
                    output_tokens = 32
                else:
                    index = state["regular"]
                    state["regular"] += 1
                    state["context_seen"].append("C09_FINITE_RECOVERY" in json.dumps(body.get("input")))
                    if index < 3:
                        phase = c09.PHASES[index]
                        item = {"type": "function_call", "id": "fc-" + phase, "call_id": "call-" + phase,
                                "name": "exec_command", "arguments": json.dumps({"cmd": c09.COMMANDS[phase],
                                    "max_output_tokens": c09.OUTPUT_TOKENS if index < 2 else 2048})}
                        output_tokens = 20000 if index < 2 else 8
                    else:
                        item = {"type": "message", "role": "assistant", "id": "final",
                                "content": [{"type": "output_text", "text": json.dumps(completed_payload())}]}
                        output_tokens = 64
                rid = "fixture-" + str(state["requests"])
                events = [
                    {"type": "response.created", "response": {"id": rid}},
                    {"type": "response.output_item.done", "output_index": 0, "item": item},
                    {"type": "response.completed", "response": {"id": rid,
                     "usage": {"input_tokens": 1000, "output_tokens": output_tokens,
                               "total_tokens": 1000 + output_tokens}}},
                ]
                response = "".join("data: " + json.dumps(e) + "\n\n" for e in events).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

        with ThreadingHTTPServer(("127.0.0.1", 0), Server) as server, tempfile.TemporaryDirectory(prefix="c09 cli ") as tmp:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            rt = Path(tmp)
            base = v7.base
            original_args = base.common_codex_args
            actual_observed = process.run_observed

            def bounded_observed(args, **kwargs):
                # The offline peer is instant. Bound a broken conformance test;
                # the live C09 timeout remains 900 seconds.
                kwargs["timeout"] = 120
                return actual_observed(args, **kwargs)

            def local_args(**kwargs):
                args = original_args(**kwargs)
                args[0] = binary
                args += ["-c", 'model_provider="fixture"', "-c", 'model_providers.fixture.name="Fixture"',
                         "-c", f'model_providers.fixture.base_url="http://127.0.0.1:{server.server_port}/v1"',
                         "-c", 'model_providers.fixture.wire_api="responses"',
                         "-c", 'model_providers.fixture.requires_openai_auth=false',
                         "-c", 'model_providers.fixture.stream_max_retries=0',
                         "-c", 'model_providers.fixture.request_max_retries=0']
                return args

            try:
                with mock.patch.dict(os.environ, {"CODEX_HOME": str(rt / "home")}), mock.patch.object(
                    base, "common_codex_args", side_effect=local_args
                ), mock.patch.object(process, "run_observed", side_effect=bounded_observed), mock.patch.object(v7.compat.v4, "_write_result", side_effect=lambda **kw: (kw["result"], True)) as writer:
                    result, _ = v7.run_c09(root=ROOT, runtime_root=rt, schemas=base.write_schemas(rt / "schemas"),
                        version=version, os_name="offline-cli", source_commit="b" * 40, date="2026-09-06")
                details = writer.call_args.kwargs
                self.assertEqual(result, "REPRODUCED", {"peer": state, "evaluation": details})
                self.assertEqual(state["compact"], 2, state)
                self.assertEqual(state["regular"], 4, state)
                self.assertEqual(state["request_kinds"],
                                 ["turn", "compaction", "turn", "compaction", "turn", "turn"])
                self.assertTrue(all(state["context_seen"]), state)
                print("CODEX_01534_OFFLINE_CONFORMANCE_OK: 3 real tools, 2 compactions, 2 compact recovery contexts, 1 completed turn")
            finally:
                server.shutdown()
                worker.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
