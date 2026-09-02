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
    def test_c13_baseline23_overlay_materializes_and_rehashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "materialized"
            written = prepare_capabilities.materialize(ROOT, target, force=True)

            c13 = target / "capabilities" / "C13"
            self.assertIn("capabilities/C13/hashes.json", written)
            self.assertIn("Baseline: `2.3`", (c13 / "README.md").read_text(encoding="utf-8"))
            self.assertIn(
                "live_codex_qualification_harness_v6.py",
                (c13 / "run-command.txt").read_text(encoding="utf-8"),
            )
            config = (c13 / "config" / "README.md").read_text(encoding="utf-8")
            self.assertIn("home-scoped", config)
            self.assertIn("project-scoped", config)
            self.assertIn("fixture_agent.toml", config)

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

    def test_overlay_does_not_remove_other_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "materialized"
            prepare_capabilities.materialize(ROOT, target, force=True)
            for capability_id in ("C01", "C06", "C12", "C16"):
                self.assertTrue((target / "capabilities" / capability_id / "expected.json").is_file())


if __name__ == "__main__":
    unittest.main()
