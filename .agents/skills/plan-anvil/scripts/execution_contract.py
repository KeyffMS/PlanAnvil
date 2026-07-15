from __future__ import annotations

import re
from typing import Any


def _section(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    body_start = start + len(heading)
    next_heading = re.search(r"(?m)^##\s+", text[body_start:])
    end = body_start + next_heading.start() if next_heading else len(text)
    return text[body_start:end].strip()


def _has(text: str, pattern: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE | re.DOTALL) is not None


def execution_contract_findings(plan_text: str) -> list[dict[str, Any]]:
    """Validate mandatory semantics of a PLAN_READY execution contract."""
    findings: list[dict[str, Any]] = []

    required_roles = {
        "Jim": r"\bJim\b",
        "Jenny": r"\bJenny\b",
        "implementation agent": r"\bimplementation agent\b",
        "independent verifier": r"\bindependent verifier\b",
        "Winston Wolfe": r"\bWinston Wolfe\b",
    }
    for role, pattern in required_roles.items():
        if not _has(plan_text, pattern):
            findings.append(
                {
                    "kind": "execution-contract-role-missing",
                    "path": "PLAN.md",
                    "role": role,
                }
            )

    if not (
        _has(plan_text, r"\bflat\b.{0,40}\bdirect[- ]child\b")
        or _has(plan_text, r"\bagents\.max_depth\s*=\s*1\b")
    ):
        findings.append(
            {
                "kind": "execution-contract-topology-missing",
                "path": "PLAN.md",
            }
        )

    if not (
        _has(plan_text, r"\bonly one agent\b.{0,80}\bmodif(?:y|ies)\b.{0,40}\bat a time\b")
        or _has(plan_text, r"\bone modifier\b.{0,40}\bat a time\b")
    ):
        findings.append(
            {
                "kind": "execution-contract-single-modifier-missing",
                "path": "PLAN.md",
            }
        )

    retry_tokens = [
        "STRATEGY-A",
        "ATTEMPT-A1",
        "ATTEMPT-A2",
        "ATTEMPT-A3",
        "STRATEGY-B",
        "ATTEMPT-B1",
        "ATTEMPT-B2",
        "ATTEMPT-B3",
    ]
    upper = plan_text.upper()
    for token in retry_tokens:
        if token not in upper:
            findings.append(
                {
                    "kind": "execution-contract-retry-missing",
                    "path": "PLAN.md",
                    "item": token,
                }
            )
    if not _has(plan_text, r"\b(?:after\s+)?six\s+(?:implementation\s+)?failures?\b"):
        findings.append(
            {
                "kind": "execution-contract-retry-missing",
                "path": "PLAN.md",
                "item": "six-failure stop",
            }
        )

    if not _has(
        plan_text,
        r"\bTask branch\b[^\n]*`?pursue/(?!plan/|integration/)[^`\s]+/[^`\s]+",
    ):
        findings.append(
            {
                "kind": "execution-contract-branch-missing",
                "path": "PLAN.md",
                "branch": "task",
            }
        )
    if not _has(
        plan_text,
        r"\bIntegration branch\b[^\n]*`?pursue/integration/[^`\s]+/[^`\s]+",
    ):
        findings.append(
            {
                "kind": "execution-contract-branch-missing",
                "path": "PLAN.md",
                "branch": "integration",
            }
        )

    testing = _section(plan_text, "## Testing and independent verification")
    cycle_markers = {
        "GREEN BASELINE": r"\bGREEN BASELINE\b",
        "EXPECTED RED": r"\bEXPECTED RED\b",
        "IMPLEMENTATION": r"\bIMPLEMENTATION\b",
        "FULL GREEN": r"\bFULL GREEN\b",
        "INDEPENDENT VERIFICATION": r"\bINDEPENDENT VERIFICATION\b",
    }
    for marker, pattern in cycle_markers.items():
        if not _has(testing, pattern):
            findings.append(
                {
                    "kind": "execution-contract-evidence-cycle-missing",
                    "path": "PLAN.md",
                    "item": marker,
                }
            )

    approvals = _section(plan_text, "## Production verification, switching, and approvals")
    if not _has(approvals, r"\bexplicit user approval\b"):
        findings.append(
            {
                "kind": "execution-contract-approval-missing",
                "path": "PLAN.md",
                "action": "explicit user approval",
            }
        )
    approval_actions = {
        "base merge or push": r"\b(?:merge|push)\b.{0,80}\bbase\b|\bbase\b.{0,80}\b(?:merge|push)\b",
        "live switching": r"\blive\b.{0,50}\b(?:switch|switching|worktree|service|environment)\b",
        "irreversible operation": r"\birreversible\b",
    }
    for action, pattern in approval_actions.items():
        if not _has(approvals, pattern):
            findings.append(
                {
                    "kind": "execution-contract-approval-missing",
                    "path": "PLAN.md",
                    "action": action,
                }
            )

    return findings
