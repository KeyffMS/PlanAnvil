from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from common import (
    PlanAnvilError,
    atomic_write_json,
    atomic_write_text,
    canonical_json_text,
    cli_main,
    discover_repo,
    emit,
    load_json,
    repo_relative,
    privacy_findings,
    sha256_file,
    sha256_text,
    utc_now,
)
from prepare_review_bundle import review_file_entries
from schema_validator import assert_valid_file, validate
from transition_state import transition_state


RESULT_RE = re.compile(r"(?im)^##\s+Result\s*$\s*`?(PASS|FAIL|BLOCKED)`?\s*$")


def _validate_review_consistency(markdown: str, result: str, findings: list[dict[str, Any]]) -> None:
    matches = RESULT_RE.findall(markdown)
    if len(matches) != 1:
        raise PlanAnvilError(
            "Blind review must contain exactly one structured Result section",
            code="REVIEW_RESULT_MISSING",
            details=matches,
        )
    markdown_result = matches[0].upper()
    if markdown_result != result:
        raise PlanAnvilError(
            f"Blind review Markdown result {markdown_result} differs from structured result {result}",
            code="REVIEW_RESULT_MISMATCH",
        )
    severe = [item for item in findings if item.get("severity") in {"HIGH", "CRITICAL"}]
    if result == "PASS" and severe:
        raise PlanAnvilError(
            "PASS is invalid when high or critical findings exist",
            code="REVIEW_PASS_WITH_BLOCKING_FINDINGS",
            details=severe,
        )
    if result == "PASS" and re.search(r"(?im)^\s*(?:conclusion\s*:\s*)?(?:FAIL|BLOCKED)\s*[.!]?\s*$", markdown):
        raise PlanAnvilError("PASS review contains a contradictory conclusion", code="REVIEW_RESULT_MISMATCH")


def record_blind_review(
    planning: Path,
    run_root: Path,
    *,
    review_markdown: Path,
    result: str,
    findings_file: Path | None = None,
) -> dict[str, Any]:
    if result not in {"PASS", "FAIL", "BLOCKED"}:
        raise PlanAnvilError(f"Invalid review result: {result}", code="INVALID_REVIEW_RESULT")
    repo = discover_repo(planning)
    run = (run_root if run_root.is_absolute() else repo / run_root).resolve()
    state = load_json(run / "state.json")
    if state.get("status") != "DETERMINISTICALLY_VALID":
        raise PlanAnvilError(
            f"Blind review recording requires DETERMINISTICALLY_VALID, found {state.get('status')}",
            code="INVALID_STATE_FOR_REVIEW",
        )

    bundle_path = run / "reports/plan-review/review-bundle.json"
    bundle = load_json(bundle_path)
    expected_files = review_file_entries(repo, run)
    if bundle.get("purpose") != "BLIND_PLAN_REVIEW" or bundle.get("files") != expected_files:
        raise PlanAnvilError(
            "Blind-review bundle membership or hashes changed after deterministic validation",
            code="REVIEW_BUNDLE_CHANGED",
        )
    for item in expected_files:
        path = repo / item["path"]
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            raise PlanAnvilError(
                f"Review input changed or is missing: {item['path']}",
                code="REVIEW_INPUT_CHANGED",
            )

    markdown = review_markdown.read_text(encoding="utf-8").rstrip() + "\n"
    if not markdown.strip():
        raise PlanAnvilError("Blind review Markdown is empty", code="EMPTY_REVIEW")
    if re.search(r"\{\{[^}]+\}\}|\b(?:TODO|TBD)\b", markdown, re.IGNORECASE):
        raise PlanAnvilError("Blind review contains placeholders", code="REVIEW_PLACEHOLDER")

    review_privacy = privacy_findings(Path("reports/plan-review/blind-review.md"), markdown)
    if review_privacy:
        raise PlanAnvilError("Blind review contains private or secret data", code="REVIEW_PRIVACY", details=review_privacy)

    findings: list[dict[str, Any]] = []
    if findings_file:
        raw = load_json(findings_file)
        if not isinstance(raw, list):
            raise PlanAnvilError("Findings file must contain a JSON array", code="INVALID_FINDINGS")
        findings = raw
    _validate_review_consistency(markdown, result, findings)

    target_md = run / "reports/plan-review/blind-review.md"
    target_json = run / "reports/plan-review/blind-review.json"
    sidecar = {
        "schema_version": "1.1.0",
        "report_type": "BLIND_PLAN_REVIEW",
        "created_at": utc_now(),
        "inputs": {item["path"]: item["sha256"] for item in expected_files},
        "result": result,
        "findings": findings,
        "markdown_hash": sha256_text(markdown),
    }
    schema = Path(__file__).resolve().parent.parent / "schemas/review.schema.json"
    schema_errors = validate(sidecar, load_json(schema))
    if schema_errors:
        raise PlanAnvilError("Blind review schema validation failed", code="SCHEMA_VALIDATION_FAILED", details=schema_errors)
    sidecar_privacy = privacy_findings(Path("reports/plan-review/blind-review.json"), canonical_json_text(sidecar))
    if sidecar_privacy:
        raise PlanAnvilError("Blind review sidecar contains private or secret data", code="REVIEW_PRIVACY", details=sidecar_privacy)
    atomic_write_text(target_md, markdown, exclusive=True)
    atomic_write_json(target_json, sidecar, exclusive=True)
    assert_valid_file(target_json, schema)

    compliance_path = run / "compliance.json"
    compliance = load_json(compliance_path)
    for capability in compliance.get("capabilities", []):
        if capability.get("id") == "CAP-BLIND-REVIEW":
            capability["status"] = "VERIFIED" if result == "PASS" else "FAILED"
            capability["evidence"] = [repo_relative(repo, target_md), repo_relative(repo, target_json)]
    compliance["verified_at"] = utc_now()
    atomic_write_json(compliance_path, compliance)

    transition_state(
        run / "state.json",
        expected_revision=state["revision"],
        new_status="BLIND_REVIEW_WRITTEN",
        phase="COMPARISON_AND_FINAL_VALIDATION",
        next_action_type="COMPARE_REVIEW",
        next_action_target="reports/plan-review/comparison.json",
        hash_paths=[target_md, target_json],
    )
    return {
        "ok": True,
        "result": "BLIND_REVIEW_WRITTEN",
        "review_result": result,
        "markdown": repo_relative(repo, target_md),
        "sidecar": repo_relative(repo, target_json),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Record one immutable PlanAnvil blind review")
    parser.add_argument("--planning", type=Path, default=Path.cwd())
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--review-markdown", type=Path, required=True)
    parser.add_argument("--result", choices=["PASS", "FAIL", "BLOCKED"], required=True)
    parser.add_argument("--findings-file", type=Path)
    args = parser.parse_args()
    payload = record_blind_review(
        args.planning,
        args.run_root,
        review_markdown=args.review_markdown,
        result=args.result,
        findings_file=args.findings_file,
    )
    return emit(payload)


if __name__ == "__main__":
    cli_main(main)
