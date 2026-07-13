from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import atomic_write_json, cli_main, discover_repo, emit, ensure_inside, load_json, utc_now


def validate_traceability(planning: Path, run_root: Path, *, write_report: bool = True) -> dict[str, Any]:
    repo = discover_repo(planning)
    run = ensure_inside(repo, run_root if run_root.is_absolute() else repo / run_root)
    trace = load_json(run / "traceability.json")
    findings: list[dict[str, Any]] = []

    criteria = trace.get("criteria") if isinstance(trace, dict) else None
    requirements = trace.get("requirements") if isinstance(trace, dict) else None
    if not isinstance(criteria, list) or not isinstance(requirements, list):
        findings.append({"kind": "traceability-root-invalid"})
        criteria = []
        requirements = []

    criterion_by_id = {
        item.get("id"): item
        for item in criteria
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }

    for requirement in requirements:
        if not isinstance(requirement, dict):
            findings.append({"kind": "requirement-invalid", "value": requirement})
            continue
        requirement_id = requirement.get("id")
        stages = requirement.get("stages")
        criterion_ids = requirement.get("criteria")
        if not isinstance(stages, list) or not all(isinstance(item, str) for item in stages):
            findings.append({"kind": "requirement-stages-invalid", "requirement": requirement_id})
            continue
        if not isinstance(criterion_ids, list) or not all(isinstance(item, str) for item in criterion_ids):
            findings.append({"kind": "requirement-criteria-invalid", "requirement": requirement_id})
            continue
        allowed_stages = set(stages)
        for criterion_id in criterion_ids:
            criterion = criterion_by_id.get(criterion_id)
            if criterion is None:
                continue
            criterion_stage = criterion.get("stage")
            if criterion_stage not in allowed_stages:
                findings.append(
                    {
                        "kind": "requirement-criterion-stage-mismatch",
                        "requirement": requirement_id,
                        "criterion": criterion_id,
                        "criterion_stage": criterion_stage,
                        "requirement_stages": sorted(allowed_stages),
                    }
                )

    payload = {
        "schema_version": "1.1.0",
        "generated_at": utc_now(),
        "validator": "validate_traceability",
        "result": "PASS" if not findings else "FAIL",
        "findings": findings,
    }
    if write_report:
        atomic_write_json(run / "reports/validation/traceability.json", payload)
    return {"ok": not findings, **payload}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate complete requirement-stage-criterion traceability")
    parser.add_argument("--planning", type=Path, default=Path.cwd())
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--no-write-report", action="store_true")
    args = parser.parse_args()
    payload = validate_traceability(args.planning, args.run_root, write_report=not args.no_write_report)
    return emit(payload, exit_code=0 if payload["ok"] else 2)


if __name__ == "__main__":
    cli_main(main)
