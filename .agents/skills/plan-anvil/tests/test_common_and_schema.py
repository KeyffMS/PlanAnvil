from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from _helpers import SCRIPTS

from common import atomic_write_json, canonical_file_is_valid, privacy_findings, sha256_text
from schema_validator import validate_file


class CommonAndSchemaTests(unittest.TestCase):
    def test_atomic_json_is_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "value.json"
            atomic_write_json(path, {"b": 2, "a": 1})
            self.assertEqual(path.read_text(encoding="utf-8"), '{\n  "a": 1,\n  "b": 2\n}\n')
            self.assertTrue(canonical_file_is_valid(path))

    def test_privacy_finds_secret_and_absolute_path(self) -> None:
        findings = privacy_findings(Path("x.md"), "password=abcdefghijklmnop\n/home/alice/repo\n")
        kinds = {item["kind"] for item in findings}
        self.assertIn("generic-token", kinds)
        self.assertIn("absolute-path", kinds)

    def _valid_manifest(self) -> dict:
        return {
            "schema_version": "1.1.0",
            "plan_id": "PG-20260712-143000-A1B2",
            "run_id": "20260712T143000Z_PG-20260712-143000-A1B2_example",
            "created_at": "2026-07-12T14:30:00Z",
            "generator_version": "0.1.0",
            "repository": {
                "fingerprint": sha256_text("repo"),
                "base_branch": "main",
                "base_sha": "a" * 40,
                "planning_branch": "pursue/plan/PG-20260712-143000-A1B2/example",
            },
            "paths": {
                "run_root": ".pursue/runs/20260712T143000Z_PG-20260712-143000-A1B2_example",
                "plan": "PLAN.md",
                "state": "state.json",
                "compliance": "compliance.json",
                "traceability": "traceability.json",
                "repository_profile": ".pursue/SYSTEM_PROFILE.md",
                "local_state": "local-state.json",
            },
            "contract_versions": {
                "implementation_spec": "2.1",
                "plan_contract": "1.0.0",
                "artifact_schema": "1.1.0",
            },
        }

    def test_manifest_schema_rejects_absolute_path(self) -> None:
        skill = SCRIPTS.parent
        schema = skill / "schemas/manifest.schema.json"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            value = self._valid_manifest()
            value["paths"]["run_root"] = "/tmp/run"
            atomic_write_json(path, value)
            errors = validate_file(path, schema)
            self.assertTrue(any("forbidden" in item or "pattern" in item for item in errors), errors)

    def test_manifest_schema_rejects_relative_traversal(self) -> None:
        schema = SCRIPTS.parent / "schemas/manifest.schema.json"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            value = self._valid_manifest()
            value["paths"]["run_root"] = "../outside"
            atomic_write_json(path, value)
            errors = validate_file(path, schema)
            self.assertTrue(any("forbidden" in item or "pattern" in item for item in errors), errors)

    def test_skill_metadata_requires_explicit_activation(self) -> None:
        skill_root = SCRIPTS.parent
        skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        metadata = (skill_root / "agents/openai.yaml").read_text(encoding="utf-8")
        self.assertIn("Use only when explicitly invoked as $plan-anvil", skill)
        self.assertIn("allow_implicit_invocation: false", metadata)
        self.assertNotIn("implement the plan in this run", skill.lower())


if __name__ == "__main__":
    unittest.main()
