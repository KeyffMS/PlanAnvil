from __future__ import annotations

import inspect
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import codex_runner_variant_matrix as matrix


class CodexRunnerVariantDispatchTests(unittest.TestCase):
    def test_run_matrix_call_shapes_bind_to_variant_helpers(self) -> None:
        inspect.signature(matrix._hook_variant).bind(
            Path("fixtures"),
            Path("output"),
            "hook_json_bash_bypass",
            "^Bash$",
            "json",
            True,
            True,
            False,
        )
        inspect.signature(matrix._compact_variant).bind(
            Path("fixtures"),
            "compact_body_after_prefix_no_budget_single",
            "body_after_prefix",
            False,
            False,
        )
        inspect.signature(matrix._subagent_variant).bind(
            Path("fixtures"),
            Path("output"),
            "subagent_v1_explicit",
            False,
            True,
            False,
        )

    def test_run_matrix_dispatches_all_fourteen_variants_without_codex(self) -> None:
        def result(name: str, log_path: str) -> dict[str, object]:
            return {
                "variant": name,
                "returncode": 0,
                "local_hook_records": {log_path: []},
            }

        def fake_hook(_root: Path, _output: Path, name: str, *_args: object) -> dict[str, object]:
            return result(name, ".diag/pretool.jsonl")

        def fake_compact(_root: Path, name: str, *_args: object) -> dict[str, object]:
            return result(name, ".diag/compact.jsonl")

        def fake_subagent(_root: Path, _output: Path, name: str, *_args: object) -> dict[str, object]:
            return result(name, ".diag/subagent.jsonl")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runtime"
            output = Path(tmp) / "artifact"
            with (
                mock.patch.object(matrix, "_hook_variant", side_effect=fake_hook) as hook,
                mock.patch.object(matrix, "_compact_variant", side_effect=fake_compact) as compact,
                mock.patch.object(matrix, "_subagent_variant", side_effect=fake_subagent) as subagent,
            ):
                results = matrix.run_matrix(root, output)

            self.assertEqual([item["variant"] for item in results], list(matrix.VARIANT_NAMES))
            self.assertEqual(hook.call_count, 6)
            self.assertEqual(compact.call_count, 4)
            self.assertEqual(subagent.call_count, 4)

            files = sorted(path.name for path in output.glob("*.json"))
            self.assertEqual(files, sorted(f"{name}.json" for name in matrix.VARIANT_NAMES))
            for path in output.glob("*.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(payload["returncode"], 0)


if __name__ == "__main__":
    unittest.main()
