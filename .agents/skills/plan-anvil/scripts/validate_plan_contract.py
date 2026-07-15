from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import atomic_write_json, cli_main, discover_repo, emit
from execution_contract import execution_contract_findings
from path_safety import assert_safe_run_root
from validate_plan import _frontmatter, validate_plan

_NON_BEHAVIOR_CLASSIFICATIONS = {
    "DOCUMENTATION",
    "NON_BEHAVIOR",
    "CONFIGURATION",
    "INFRASTRUCTURE",
    "REFACTOR_NO_BEHAVIOR_CHANGE",
}


def validate_plan_contract(planning: Path, run_root: Path, *, write_report: bool = True) -> dict[str, Any]:
    repo = discover_repo(planning)
    run = assert_safe_run_root(repo, run_root)
    result = validate_plan(repo, run, write_report=False)
    classifications: dict[str, str] = {}
    for path in sorted((run / "stages").glob("STAGE-*.md")):
        try:
            metadata = _frontmatter(path)
        except Exception:
            continue
        stage_id = metadata.get("stage_id")
        classification = metadata.get("classification")
        if isinstance(stage_id, str) and isinstance(classification, str):
            classifications[stage_id] = classification.strip().upper()

    filtered: list[dict[str, Any]] = []
    for finding in result.get("findings", []):
        if (
            finding.get("kind") == "stage-evidence-cycle-incomplete"
            and finding.get("missing") == "RED"
            and classifications.get(finding.get("stage")) in _NON_BEHAVIOR_CLASSIFICATIONS
        ):
            continue
        filtered.append(finding)

    plan_path = run / "PLAN.md"
    if result.get("plan_status") == "PLAN_READY" and plan_path.is_file():
        filtered.extend(execution_contract_findings(plan_path.read_text(encoding="utf-8")))

    payload = {**result, "findings": filtered, "result": "PASS" if not filtered else "FAIL"}
    payload["ok"] = not filtered
    if write_report:
        atomic_write_json(
            run / "reports/validation/plan.json",
            {key: value for key, value in payload.items() if key != "ok"},
        )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate PlanAnvil plan with classification-aware evidence cycles")
    parser.add_argument("--planning", type=Path, default=Path.cwd())
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--no-write-report", action="store_true")
    args = parser.parse_args()
    payload = validate_plan_contract(args.planning, args.run_root, write_report=not args.no_write_report)
    return emit(payload, exit_code=0 if payload["ok"] else 2)


if __name__ == "__main__":
    cli_main(main)
