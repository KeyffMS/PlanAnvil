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
    sha256_text,
    utc_now,
)
from prepare_review_bundle import review_file_entries
from schema_validator import assert_valid_file
from transition_state import run_lock, transition_state


def _hash_or_missing(path: Path) -> str:
    return sha256_file(path) if path.is_file() else sha256_text(f"missing:{path.name}")


def compare_review(planning: Path, run_root: Path) -> dict[str, Any]:
    repo = discover_repo(planning)
    run = (run_root if run_root.is_absolute() else repo / run_root).resolve()
    state_path = run / "state.json"
    target = run / "reports/plan-review/comparison.json"

    with run_lock(state_path, command="compare-review"):
        state = load_json(state_path)
        if state.get("status") != "BLIND_REVIEW_WRITTEN":
            raise PlanAnvilError(
                f"Comparison requires BLIND_REVIEW_WRITTEN, found {state.get('status')}",
                code="INVALID_STATE_FOR_COMPARISON",
            )

        review_md = run / "reports/plan-review/blind-review.md"
        review_json = run / "reports/plan-review/blind-review.json"
        summary_path = run / "reports/validation/summary.json"
        bundle_path = run / "reports/plan-review/review-bundle.json"

        reasons: list[str] = []
        try:
            sidecar = load_json(review_json)
        except PlanAnvilError:
            sidecar = {}
            reasons.append("Blind-review sidecar is missing or invalid.")
        summary = load_json(summary_path) if summary_path.is_file() else {}
        bundle = load_json(bundle_path) if bundle_path.is_file() else {}

        try:
            current_files = review_file_entries(repo, run)
        except PlanAnvilError as exc:
            current_files = []
            reasons.append(f"Review bundle input is missing: {exc}.")

        expected_inputs = {item["path"]: item["sha256"] for item in current_files}
        if bundle.get("purpose") != "BLIND_PLAN_REVIEW":
            reasons.append("Review bundle purpose is missing or invalid.")
        if bundle.get("files") != current_files:
            reasons.append("Review bundle membership or input hashes changed after review.")
        if sidecar.get("inputs") != expected_inputs:
            reasons.append("Blind-review sidecar inputs do not match current bundle inputs.")

        review_md_hash = _hash_or_missing(review_md)
        review_json_hash = _hash_or_missing(review_json)
        if review_md_hash != sidecar.get("markdown_hash"):
            reasons.append("Blind-review Markdown hash does not match its immutable sidecar.")

        recorded_hashes = state.get("artifact_hashes", {})
        expected_md_key = "reports/plan-review/blind-review.md"
        expected_json_key = "reports/plan-review/blind-review.json"
        if recorded_hashes.get(expected_md_key) != review_md_hash:
            reasons.append("Canonical state hash for blind-review Markdown is stale.")
        if recorded_hashes.get(expected_json_key) != review_json_hash:
            reasons.append("Canonical state hash for blind-review sidecar is stale.")

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
            "blind_review_hash": review_md_hash,
            "blind_review_sidecar_hash": review_json_hash,
            "deterministic_validation": "PASS" if summary.get("result") == "PASS" else ("FAIL" if summary else "MISSING"),
            "reasons": reasons,
        }

        created = False
        try:
            atomic_write_json(target, comparison, exclusive=True)
            created = True
            schema = Path(__file__).resolve().parent.parent / "schemas/comparison.schema.json"
            assert_valid_file(target, schema)

            transition_state(
                state_path,
                expected_revision=state["revision"],
                new_status="COMPARISON_VALID" if result == "PASS" else "FAILED",
                phase="COMMIT_PLANNING_ARTIFACTS" if result == "PASS" else "REPORT_AND_STOP",
                next_action_type="COMMIT_PLAN" if result == "PASS" else "NONE",
                next_action_target=repo_relative(repo, run) if result == "PASS" else None,
                blocker=None if result == "PASS" else "PLAN_VALIDATION_FAILED",
                hash_paths=[target],
                lock_held=True,
            )
        except Exception:
            if created:
                target.unlink(missing_ok=True)
            raise

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
