from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".agents" / "skills" / "plan-anvil" / "SKILL.md"
CONTRACT = ROOT / ".agents" / "skills" / "plan-anvil" / "references" / "codex-0.152-contract.md"
EXECUTION = ROOT / ".agents" / "skills" / "plan-anvil" / "references" / "execution-contract.md"
TEMPLATE = ROOT / ".agents" / "skills" / "plan-anvil" / "templates" / "PLAN.md"
GOLDEN = ROOT / "examples" / "small-change" / "run" / "PLAN.md"
COMPAT = ROOT / "tools" / "live_codex_qualification_codex0152.py"
SCRIPTS = ROOT / ".agents" / "skills" / "plan-anvil" / "scripts"


class Codex0152ProductAlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = SKILL.read_text(encoding="utf-8")
        cls.contract = CONTRACT.read_text(encoding="utf-8")
        cls.execution = EXECUTION.read_text(encoding="utf-8")
        cls.template = TEMPLATE.read_text(encoding="utf-8")
        cls.golden = GOLDEN.read_text(encoding="utf-8")
        cls.compat = COMPAT.read_text(encoding="utf-8")

    def test_product_requires_exact_subagent_roles(self) -> None:
        self.assertIn("exact `agent_type` `plan_anvil_profiler`", self.skill)
        self.assertIn("exact `agent_type` `plan_anvil_reviewer`", self.skill)
        self.assertIn("`SubagentStart` matcher input is the spawned `agent_type`", self.contract)
        self.assertIn("`plan_anvil_profiler`", self.contract)
        self.assertIn("`plan_anvil_reviewer`", self.contract)

    def test_product_has_deterministic_mutation_postcondition(self) -> None:
        self.assertIn("hook enforcement is an early guard only", self.contract)
        self.assertIn("deterministic planning-diff/source-immutability validator is authoritative", self.contract)
        self.assertIn("immediately run `validate_diff.py", self.skill)
        self.assertIn("after every file-changing tool call", self.template)
        self.assertIn("actual changed paths", self.execution)

    def test_product_keeps_user_token_budget_semantics(self) -> None:
        self.assertIn("must not disable a user's TokenBudget configuration", self.contract)
        self.assertIn("Qualification may disable the fallback buffer only in an isolated fixture", self.contract)
        product_config = (ROOT / ".codex" / "config.toml").read_text(encoding="utf-8")
        self.assertNotIn("token_budget", product_config)

    def test_qualification_disables_token_budget_only_in_isolated_compaction_fixture(self) -> None:
        self.assertIn('v4._set_compact_config = set_compact_config', self.compat)
        self.assertIn('_set_feature(text, "token_budget", "false")', self.compat)
        self.assertIn("finally:\n        v4._set_compact_config = old_set", self.compat)

    def test_c06_qualifies_codex0152_guaranteed_hook_and_product_postcondition(self) -> None:
        self.assertIn("C06_SUPPORTED_HOOK", self.compat)
        self.assertIn('item.get("tool_name") == "Bash"', self.compat)
        self.assertIn("file_change_postcondition", self.compat)
        self.assertIn("postcondition_detected", self.compat)
        self.assertNotIn("minimal_apply_patch_pretooluse", self.compat)

    def test_c13_qualification_uses_exact_agent_type(self) -> None:
        self.assertIn("agent_type` exactly `fixture_agent`", self.compat)
        self.assertIn("do not use a default/unnamed", self.compat)
        self.assertIn("continue=false", self.compat)
        self.assertIn("must not be treated as a stop control", self.compat)

    def test_template_and_golden_are_contract_23(self) -> None:
        self.assertIn("Contract: PlanAnvil 2.3", self.template)
        self.assertIn("Contract: PlanAnvil 2.3", self.golden)

    def test_golden_satisfies_full_execution_contract(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        try:
            from execution_contract import execution_contract_findings
        finally:
            sys.path.pop(0)
        self.assertEqual(execution_contract_findings(self.golden), [])


if __name__ == "__main__":
    unittest.main()
