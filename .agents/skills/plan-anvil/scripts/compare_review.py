from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import (
    PlanAnvilError,
    atomic_write_json,
    cli_main,
    discover_repo,
    emit,
    load_json,
    repo_relative,
    sha256_file,
    utc_now,
)
from schema_validator import assert_valid_file
from transition_state import transition_state


def compare_review(planning: Path, run_root: Path) -> dict[str, Any]:
    repo = discover_repo(planning)
    run = (run_root if run_root.is_absolute() else repo / run_root).resolve()
    state = load_json(run / "state.json")
    if state.get("status") != "BLIND_REVIEW_WRITTEN":
        raise PlanAnvilError(
            f"Comparison requires BLIND_REVIEW_WRITTEN, found {state.get('status')}",
            code="INVALID_STATE_FOR_COMPARISON",
        )

    review_md = run / "reports/plan-review/blind-review.md"
    review_json = run / "reports/plan-review/blind-review.json"
    sidecar = load_json(review_json)
    summary_path = run / "reports/validation/summary.json"
    summary = load_json(summary_path) if summary_path.is_file() else {}

    reasons: list[str] = []
    if sha256_file(review_md) != sidecar.get("markdown_hash"):
        reasons.append("Blind-review Markdown hash does not match its immutable sidecar.")
    if sidecar.get("result") != "PASS":
        reasons.append(f"Blind review result is {sidecar.get('result')}.")
    if summary.get("result") != "PASS":
        reasons.append("Deterministic validation is missing or failed.")
    high_findings = [
        item for item in sidecar.get("findings", [])
        if item.get("severity") in {"HIGH", "CRITICAL"}
    ]
    if high_findings:
        reasons.append("Blind review contains high or critical findings.")

    result = "PASS" if not reasons else "FAIL"
    comparison = {
        "schema_version": "1.1.0",
        "created_at": utc_now(),
        "result": result,
        "blind_review_hash": sha256_file(review_md),
        "blind_review_sidecar_hash": sha256_file(review_json),
        "deterministic_validation": "PASS" if summary.get("result") == "PASS" else ("FAIL" if summary else "MISSING"),
        "reasons": reasons,
    }
    target = run / "reports/plan-review/comparison.json"
    atomic_write_json(target, comparison, exclusive=True)
    schema = Path(__file__).resolve().parent.parent / "schemas/comparison.schema.json"
    assert_valid_file(target, schema)

    if result == "PASS":
        transition_state(
            run / "state.json",
            expected_revision=state["revision"],
            new_status="COMPARISON_VALID",
            phase="COMMIT_PLANNING_ARTIFACTS",
            next_action_type="COMMIT_PLAN",
            next_action_target=repo_relative(repo, run),
            hash_paths=[target],
        )
    else:
        transition_state(
            run / "state.json",
            expected_revision=state["revision"],
            new_status="FAILED",
            phase="REPORT_AND_STOP",
            next_action_type="NONE",
            next_action_target=None,
            blocker="PLAN_VALIDATION_FAILED",
            hash_paths=[target],
        )
    return {
        "ok": result == "PASS",
        "result": result,
        "comparison": repo_relative(repo, target),
        "reasons": reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare immutable blind review with deterministic PlanAnvil validation")
    parser.add_argument("--planning", type=Path, default=Path.cwd())
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    payload = compare_review(args.planning, args.run_root)
    return emit(payload, exit_code=0 if payload["ok"] else 2)


if __name__ == "__main__":
    cli_main(main)
