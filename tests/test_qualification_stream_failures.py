from __future__ import annotations

import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import qualification_process as process
import live_codex_qualification_harness_v4 as v4


class StreamFailureTests(unittest.TestCase):
    def test_deeply_nested_json_is_counted_without_losing_next_event(self) -> None:
        collector = process.StructuralEvents()
        depth = sys.getrecursionlimit() + 100
        stream = io.BytesIO(b"[" * depth + b"0" + b"]" * depth + b'\n{"type":"turn.completed"}\n')
        collector.read(stream)
        result = collector.summary()
        self.assertEqual(result["invalid_json_lines"], 1)
        self.assertEqual(result["event_types"], {"turn.completed": 1})
        self.assertFalse(result["reader_failed"])

    def test_unexpected_reader_exception_sets_fail_closed_flag(self) -> None:
        pipe = mock.Mock()
        pipe.readline.side_effect = RuntimeError("synthetic private diagnostic")
        collector = process.StructuralEvents()
        collector.read(pipe)
        self.assertTrue(collector.summary()["reader_failed"])
        self.assertNotIn("synthetic private diagnostic", str(collector.summary()))
        pipe.close.assert_called_once_with()

    def test_cleanup_and_reader_failures_never_accept_positive_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for diagnostic in (
                {"process_cleanup_ok": False},
                {"process_cleanup_ok": True, "reader_failed": True},
            ):
                with self.subTest(diagnostic=diagnostic):
                    def run(args, **kwargs):
                        v4.base.json_dump(root / "trial-01.json", {"outcome": "PASS"})
                        return process.ProcessResult(0, False, diagnostic)
                    with mock.patch.object(process, "run_observed", side_effect=run):
                        payload, events, error = v4._run_codex_probe(
                            cwd=root, prompt="offline", schemas={"trial": root / "schema.json"},
                            results_dir=root, position=1, sandbox="read-only", observe_process=True,
                        )
                    self.assertEqual(payload, {})
                    self.assertIsNotNone(error)
                    self.assertEqual(events, diagnostic)


if __name__ == "__main__":
    unittest.main()
