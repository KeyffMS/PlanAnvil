from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import PlanAnvilError, cli_main, discover_repo, emit, ensure_inside, load_json
from transition_state import transition_state
from validate_artifacts import validate_artifacts
from validate_plan import validate_plan


def seal_artifacts(planning: Path, run_root: Path) -> dict[str, Any]:
    repo = discover_repo(planning)
    run = ensure_inside(repo, run_root if run_root.is_absolute() else repo / run_root)
    state = load_json(run / "state.json")
    if state.get("status") != "ANALYSIS_READY":
        raise PlanAnvilError(
            f"Artifact sealing requires ANALYSIS_READY, found {state.get('status')}",
            code="INVALID_STATE_FOR_ARTIFACT_SEAL",
        )
    plan_result = validate_plan(repo, run, write_report=False)
    artifact_result = validate_artifacts(repo, run, phase="pre-review", write_report=False)
    findings = []
    if not plan_result.get("ok"):
        findings.append({"validator": "validate_plan", "findings": plan_result.get("findings", [])})
    if not artifact_result.get("ok"):
        findings.append({"validator": "validate_artifacts", "findings": artifact_result.get("findings", [])})
    if findings:
        raise PlanAnvilError("Plan artifacts are incomplete or invalid", code="ARTIFACT_SEAL_FAILED", details=findings)

    plan_status = plan_result.get("plan_status")
    if plan_status != "PLAN_READY":
        raise PlanAnvilError(
            f"Only PLAN_READY artifacts can be sealed, found {plan_status}",
            code="PLAN_NOT_READY_TO_SEAL",
        )
    hash_paths = [run / "PLAN.md", run / "traceability.json", run / "evidence/analysis.json"]
    hash_paths.extend(sorted((run / "stages").glob("STAGE-*.md")))
    hash_paths.extend(sorted((run / "risks").glob("RISK-*.json")))
    transition_state(
        run / "state.json",
        expected_revision=state["revision"],
        new_status="ARTIFACTS_GENERATED",
        phase="DETERMINISTIC_VALIDATION",
        next_action_type="RUN_VALIDATOR",
        next_action_target="reports/validation/summary.json",
        hash_paths=hash_paths,
    )
    return {"ok": True, "result": "ARTIFACTS_GENERATED", "artifacts": len(hash_paths)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Seal authored PlanAnvil artifacts before deterministic validation")
    parser.add_argument("--planning", type=Path, default=Path.cwd())
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    return emit(seal_artifacts(args.planning, args.run_root))


if __name__ == "__main__":
    cli_main(main)
