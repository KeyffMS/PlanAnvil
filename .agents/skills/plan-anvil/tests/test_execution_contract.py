from __future__ import annotations

import unittest

from execution_contract import execution_contract_findings


def compliant_plan() -> str:
    return """# Plan

## Testing and independent verification

Behavior-changing stages use GREEN BASELINE → EXPECTED RED → IMPLEMENTATION → FULL GREEN → INDEPENDENT VERIFICATION.

## Git, integration, and control-root rules

Jim coordinates a flat direct-child topology. Jenny owns approved tests, one implementation agent owns approved product paths, an independent verifier remains read-only, and Winston Wolfe performs read-only incident analysis after six failures. Only one agent may modify repository files at a time.

Retry model: STRATEGY-A uses ATTEMPT-A1, ATTEMPT-A2, ATTEMPT-A3. STRATEGY-B uses ATTEMPT-B1, ATTEMPT-B2, ATTEMPT-B3. After six failures, Winston Wolfe performs read-only incident analysis and execution stops.

Task branch: `pursue/PG-20260101-000000-ABCD/feature`.
Integration branch: `pursue/integration/PG-20260101-000000-ABCD/feature`.

## Production verification, switching, and approvals

Explicit user approval is required before a base-branch merge or push, switching a live worktree, service, or environment, and any irreversible operation.
"""


class ExecutionContractTests(unittest.TestCase):
    def test_complete_contract_passes(self) -> None:
        self.assertEqual(execution_contract_findings(compliant_plan()), [])

    def test_each_required_role_is_enforced(self) -> None:
        replacements = {
            "Jim": "Coordinator",
            "Jenny": "Test owner",
            "implementation agent": "modifier",
            "independent verifier": "reviewer",
            "Winston Wolfe": "incident analyst",
        }
        for role, replacement in replacements.items():
            with self.subTest(role=role):
                findings = execution_contract_findings(compliant_plan().replace(role, replacement))
                self.assertIn(
                    {
                        "kind": "execution-contract-role-missing",
                        "path": "PLAN.md",
                        "role": role,
                    },
                    findings,
                )

    def test_retry_model_is_enforced(self) -> None:
        findings = execution_contract_findings(compliant_plan().replace("ATTEMPT-B3", "FINAL-B"))
        self.assertIn(
            {
                "kind": "execution-contract-retry-missing",
                "path": "PLAN.md",
                "item": "ATTEMPT-B3",
            },
            findings,
        )

    def test_branch_names_are_enforced(self) -> None:
        findings = execution_contract_findings(
            compliant_plan().replace(
                "Integration branch: `pursue/integration/PG-20260101-000000-ABCD/feature`.",
                "Integration work is unspecified.",
            )
        )
        self.assertIn(
            {
                "kind": "execution-contract-branch-missing",
                "path": "PLAN.md",
                "branch": "integration",
            },
            findings,
        )

    def test_flat_topology_and_single_modifier_are_enforced(self) -> None:
        text = compliant_plan().replace("flat direct-child topology", "team topology")
        text = text.replace("Only one agent may modify repository files at a time.", "Agents coordinate changes.")
        kinds = {item["kind"] for item in execution_contract_findings(text)}
        self.assertIn("execution-contract-topology-missing", kinds)
        self.assertIn("execution-contract-single-modifier-missing", kinds)

    def test_evidence_cycle_is_enforced(self) -> None:
        findings = execution_contract_findings(compliant_plan().replace("FULL GREEN", "TEST AGAIN"))
        self.assertIn(
            {
                "kind": "execution-contract-evidence-cycle-missing",
                "path": "PLAN.md",
                "item": "FULL GREEN",
            },
            findings,
        )

    def test_all_approval_gates_are_enforced(self) -> None:
        findings = execution_contract_findings(compliant_plan().replace("irreversible operation", "high-risk operation"))
        self.assertIn(
            {
                "kind": "execution-contract-approval-missing",
                "path": "PLAN.md",
                "action": "irreversible operation",
            },
            findings,
        )


if __name__ == "__main__":
    unittest.main()
