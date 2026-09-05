from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import prepare_capabilities
import validate_capabilities


class CapabilityMaterializerOverlayTests(unittest.TestCase):
    def test_c06_codex0152_overlay_materializes_and_rehashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "materialized"
            written = prepare_capabilities.materialize(ROOT, target, force=True)

            c06 = target / "capabilities" / "C06"
            self.assertIn("capabilities/C06/hashes.json", written)
            readme = (c06 / "README.md").read_text(encoding="utf-8")
            self.assertIn("Codex CLI `0.152.x`", readme)
            self.assertIn("canonical tool name `Bash`", readme)
            self.assertIn("deterministic Git/filesystem postcondition", readme)
            prompt = (c06 / "prompt.txt").read_text(encoding="utf-8")
            self.assertIn("exec_command", prompt)
            self.assertIn("missing hook telemetry", prompt)

            self.assertEqual(validate_capabilities.validate_all(target), [])

    def test_c13_baseline23_overlay_materializes_and_rehashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "materialized"
            written = prepare_capabilities.materialize(ROOT, target, force=True)

            c13 = target / "capabilities" / "C13"
            self.assertIn("capabilities/C13/hashes.json", written)
            readme = (c13 / "README.md").read_text(encoding="utf-8")
            self.assertIn("Baseline: `2.3`", readme)
            self.assertIn("agent_type", readme)
            self.assertIn("fixture_agent", readme)
            self.assertIn(
                "live_codex_qualification_harness_v7.py",
                (c13 / "run-command.txt").read_text(encoding="utf-8"),
            )
            config = (c13 / "config" / "README.md").read_text(encoding="utf-8")
            self.assertIn("No home-scoped synthetic agent or hook substitutes", config)
            self.assertIn("project-scoped", config)
            self.assertIn("[agents.fixture_agent]", config)
            self.assertIn('config_file = "./agents/fixture_agent.toml"', config)
            self.assertIn("agent_type=fixture_agent", config)
            prompt = (c13 / "prompt.txt").read_text(encoding="utf-8")
            self.assertIn("agent_type` exactly `fixture_agent", prompt)
            self.assertIn("not a stop control", prompt)

            expected = json.loads((c13 / "expected.json").read_text(encoding="utf-8"))
            self.assertEqual(
                expected["assertions"],
                [
                    "SubagentStart can add context for the starting agent.",
                    "continue=false does not become a relied-upon startup blocker.",
                ],
            )
            index = json.loads((target / "capabilities" / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["baseline_version"], "2.3")
            self.assertEqual(validate_capabilities.validate_all(target), [])

    def test_recovery_overlays_do_not_change_expected_assertions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            prepare_capabilities.materialize(ROOT, target, force=True)
            expected = {
                "C09": ["Valid checkpoint allows compaction.",
                        "Recovery reconciles canonical files/Git after compaction.",
                        "A second valid compaction path is not permanently blocked."],
                "C10": ["Recovery hook injects a pointer/context, not hidden mutable state.",
                        "Session continuation can reconstruct from canonical files and Git."],
            }
            for cid, assertions in expected.items():
                directory = target / "capabilities" / cid
                package = json.loads((directory / "expected.json").read_text(encoding="utf-8"))
                self.assertEqual(package["assertions"], assertions)
                self.assertIn("live_codex_qualification_recovery.py",
                              (directory / "run-command.txt").read_text(encoding="utf-8"))
            self.assertIn("BEFORE", (target / "capabilities/C10/fixture/README.md").read_text(encoding="utf-8"))
            self.assertIn("timeout", (target / "capabilities/C09/fixture/README.md").read_text(encoding="utf-8"))
            self.assertEqual(validate_capabilities.validate_all(target), [])

    def test_overlays_do_not_remove_other_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "materialized"
            prepare_capabilities.materialize(ROOT, target, force=True)
            for capability_id in ("C01", "C06", "C12", "C13", "C16"):
                self.assertTrue((target / "capabilities" / capability_id / "expected.json").is_file())


if __name__ == "__main__":
    unittest.main()
