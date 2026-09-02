from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "live_codex_qualification_harness_v3.py"
sys.path.insert(0, str(ROOT / "tools"))
SPEC = importlib.util.spec_from_file_location("live_codex_qualification_harness_v3", MODULE_PATH)
assert SPEC and SPEC.loader
harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(harness)


class LiveCodexHarnessV3Tests(unittest.TestCase):
    def test_only_c12_is_overridden(self) -> None:
        self.assertEqual(harness.TARGET_CAPABILITIES, {"C12"})
        self.assertIs(harness._ORIGINAL_CAPABILITY_RUNTIME, harness.prior.capability_runtime)

    def test_fixture_places_secret_tail_beyond_budget(self) -> None:
        data = harness._build_agents_fixture("HEADSECRET", "TAILSECRET")
        self.assertEqual(len(data), harness.C12_FIXTURE_BYTES)
        self.assertLess(data.index(b"HEADSECRET"), harness.C12_LIMIT_BYTES)
        self.assertGreater(data.index(b"TAILSECRET"), harness.C12_LIMIT_BYTES)
        self.assertEqual(data.index(b"C12_TAIL_TOKEN"), harness.C12_TAIL_OFFSET + 1)
        self.assertNotIn(b"TAILSECRET", data[: harness.C12_LIMIT_BYTES])

    def test_runtime_limit_is_redundantly_enforced(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn('project_doc_max_bytes = {C12_LIMIT_BYTES}', source)
        self.assertIn('project_doc_max_bytes={C12_LIMIT_BYTES}', source)
        self.assertIn('"--sandbox"', (ROOT / "tools" / "live_codex_qualification.py").read_text(encoding="utf-8"))
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", source)

    def test_automatic_probe_rejects_tool_contamination(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("Do not run shell commands, do not use tools", source)
        self.assertIn('events.get("completed_command_items")', source)
        self.assertIn("tail_observed", source)
        self.assertIn("head_observed", source)

    def test_plananvil_full_read_is_outer_deterministic_evidence(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("from map_instructions import map_instructions", source)
        self.assertIn("automatic_byte_limit", source)
        self.assertIn("full_read", source)
        self.assertIn("truncation_risk", source)
        self.assertIn("outer deterministic PlanAnvil map_instructions", source)


if __name__ == "__main__":
    unittest.main()
