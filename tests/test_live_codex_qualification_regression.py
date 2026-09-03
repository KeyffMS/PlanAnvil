from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "tools" / "live_codex_qualification_regression.py"
AUDIT_PATH = ROOT / "docs" / "CODEX_QUALIFICATION_REGRESSION_AUDIT_2026-09-03.md"


class QualificationRegressionAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE_PATH.read_text(encoding="utf-8")
        cls.audit = AUDIT_PATH.read_text(encoding="utf-8")

    def test_exact_audited_capability_set(self) -> None:
        self.assertIn('TARGET_CAPABILITIES = {"C03", "C06", "C08", "C09", "C13", "C16"}', self.source)

    def test_hook_telemetry_is_external_and_fail_open(self) -> None:
        self.assertIn('HOOK_LOG_ENV = "PLANANVIL_QUAL_HOOK_LOG"', self.source)
        self.assertIn('os.environ["TMPDIR"] = str(path.parent.resolve())', self.source)
        self.assertIn('os.environ[HOOK_LOG_ENV] = str(path.resolve())', self.source)
        self.assertIn("except Exception:\n    pass\n# Recorder failure is never allowed to change the hook result.", self.source)
        recorder_index = self.source.index("except Exception:\n    pass\n# Recorder failure is never allowed to change the hook result.")
        stdout_index = self.source.index("sys.stdout.write(completed.stdout)")
        self.assertLess(recorder_index, stdout_index)
        self.assertNotIn('qualification-hook-events.jsonl"\nlog.parent.mkdir', self.source)

    def test_compaction_repairs_use_low_redundant_triggers(self) -> None:
        self.assertIn("v4.C08_COMPACT_LIMIT = 40", self.source)
        self.assertIn("v4.C09_COMPACT_LIMIT = 200", self.source)
        self.assertIn("expanded = [name for name in names for _ in range(2)]", self.source)
        self.assertIn("return v4._c08_runtime(**kwargs)", self.source)
        self.assertIn("return v4._c09_runtime(**kwargs)", self.source)

    def test_c03_uses_explicit_auxiliary_git_source_and_outer_decision(self) -> None:
        self.assertIn('source = worktrees / "source"', self.source)
        self.assertIn('planning = worktrees / "planning"', self.source)
        self.assertIn('"plan_anvil.py", "start"', self.source)
        self.assertIn("source_core_unchanged", self.source)
        self.assertIn("execution_contract_findings", self.source)
        self.assertIn("flat\\s+direct[- ]child\\s+topology", self.source)
        c03 = self.source[self.source.index("def run_c03("):self.source.index("# C06")]
        self.assertNotIn("evaluator", c03.lower())

    def test_c06_has_integrated_and_minimal_apply_patch_repros(self) -> None:
        self.assertIn('"matcher": "^apply_patch$"', self.source)
        self.assertIn("minimal_apply_patch_pretooluse", self.source)
        self.assertIn("supported_apply_patch", self.source)
        self.assertIn("The isolated PreToolUse hook fired, but the installed PlanAnvil PreToolUse hook did not.", self.source)
        self.assertIn("Direct apply_patch completed but the isolated current-runtime PreToolUse hook did not fire.", self.source)
        self.assertIn("outer_non_intercepted_postcondition", self.source)

    def test_c13_reuses_baseline23_transport_with_repaired_telemetry(self) -> None:
        self.assertIn("def run_c13(current_runtime", self.source)
        self.assertIn("_patched_v5_c13", self.source)
        self.assertIn("v5._c13_hook_proxy_source = _fail_open_proxy_source", self.source)
        self.assertIn("v5._run_c13_codex = run_c13", self.source)

    def test_c16_uses_outer_diagnostic_basis_without_raw_diagnostics(self) -> None:
        self.assertIn("def _outer_probe", self.source)
        self.assertIn("signing_diagnostic_observed", self.source)
        self.assertIn("hook_diagnostic_observed", self.source)
        self.assertIn('"raw_diagnostics_retained=false"', self.source)
        c16 = self.source[self.source.index("def run_c16("):]
        self.assertNotIn("evaluator", c16.lower())

    def test_safety_invariants(self) -> None:
        for forbidden in (
            "--dangerously-bypass-approvals-and-sandbox",
            "danger-full-access",
            "--privileged",
            "SYS_ADMIN",
        ):
            self.assertNotIn(forbidden, self.source)
        self.assertIn('sandbox="workspace-write"', self.source)
        self.assertIn("_patched_v4", self.source)
        self.assertIn("_patched_v5_c13", self.source)

    def test_audit_records_root_causes_and_exit_gate(self) -> None:
        for marker in (
            "R1 — read-only hook telemetry",
            "R4 — C03",
            "R5 — C16",
            "R6 — C06",
            "R8 — wrapper-chain growth",
            "no full/self-hosted qualification is run until hosted regression tests",
        ):
            self.assertIn(marker, self.audit)


if __name__ == "__main__":
    unittest.main()
