from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from common import (
    PlanAnvilError,
    SCHEMA_VERSION,
    atomic_write_json,
    atomic_write_text,
    canonical_json_text,
    cli_main,
    discover_repo,
    emit,
    ensure_inside,
    load_json,
    privacy_findings,
    repo_relative,
    sha256_file,
    sha256_text,
    utc_now,
)
from schema_validator import assert_valid_file, validate
from transition_state import run_lock, transition_state


CLASSIFICATIONS = {
    "ISOLATED", "CROSS_COMPONENT", "STATEFUL", "PUBLIC_API",
    "SECURITY", "LIVE_OPERATION", "DOCUMENTATION",
}
RISKS = {"LOW", "MEDIUM", "HIGH"}
CONFIDENCE = {"VERIFIED", "USER_CONFIRMED", "INFERRED"}


def _relative_existing(repo: Path, value: str, *, code: str) -> str:
    candidate = ensure_inside(repo, repo / value)
    if not candidate.exists():
        raise PlanAnvilError(f"Evidence path does not exist: {value}", code=code)
    return repo_relative(repo, candidate)


def record_analysis(
    planning: Path,
    run_root: Path,
    *,
    analysis_markdown: Path,
    analysis_data: Path,
) -> dict[str, Any]:
    repo = discover_repo(planning)
    run = ensure_inside(repo, run_root if run_root.is_absolute() else repo / run_root)
    state_path = run / "state.json"
    target_md = run / "evidence/analysis.md"
    target_json = run / "evidence/analysis.json"

    with run_lock(state_path, command="record-analysis"):
        state = load_json(state_path)
        if state.get("status") != "INSTRUCTION_MAP_READY":
            raise PlanAnvilError(
                f"Analysis requires INSTRUCTION_MAP_READY, found {state.get('status')}",
                code="INVALID_STATE_FOR_ANALYSIS",
            )

        markdown = analysis_markdown.read_text(encoding="utf-8").rstrip() + "\n"
        if not markdown.strip():
            raise PlanAnvilError("Analysis Markdown is empty", code="EMPTY_ANALYSIS")
        if re.search(r"\{\{[^}]+\}\}|\b(?:TODO|TBD)\b", markdown, re.IGNORECASE):
            raise PlanAnvilError("Analysis contains placeholders", code="ANALYSIS_PLACEHOLDER")
        findings = privacy_findings(Path("evidence/analysis.md"), markdown)
        if findings:
            raise PlanAnvilError("Analysis contains private or secret data", code="ANALYSIS_PRIVACY", details=findings)

        raw = load_json(analysis_data)
        if not isinstance(raw, dict):
            raise PlanAnvilError("Analysis data must be a JSON object", code="INVALID_ANALYSIS_DATA")
        allowed = {"classification", "risk", "affected_paths", "evidence", "assumptions", "unknowns"}
        unexpected = sorted(set(raw) - allowed)
        if unexpected:
            raise PlanAnvilError("Analysis data has unexpected fields", code="INVALID_ANALYSIS_DATA", details=unexpected)
        if raw.get("classification") not in CLASSIFICATIONS or raw.get("risk") not in RISKS:
            raise PlanAnvilError("Invalid analysis classification or risk", code="INVALID_ANALYSIS_DATA")

        instruction_map = load_json(run / "evidence/instruction-map.json")
        mapped_paths = set(instruction_map.get("affected_paths", []))
        affected = []
        for value in raw.get("affected_paths", []):
            if not isinstance(value, str):
                raise PlanAnvilError("Affected paths must be strings", code="INVALID_ANALYSIS_DATA")
            rel = repo_relative(repo, ensure_inside(repo, repo / value))
            if rel not in mapped_paths:
                raise PlanAnvilError(
                    f"Affected path is not covered by the instruction map: {rel}",
                    code="UNMAPPED_AFFECTED_PATH",
                )
            affected.append(rel)
        if not affected:
            raise PlanAnvilError("At least one affected path is required", code="INVALID_ANALYSIS_DATA")

        evidence = [_relative_existing(repo, item, code="ANALYSIS_EVIDENCE_MISSING") for item in raw.get("evidence", [])]
        assumptions = raw.get("assumptions", [])
        unknowns = raw.get("unknowns", [])
        if not isinstance(assumptions, list) or not isinstance(unknowns, list):
            raise PlanAnvilError("Assumptions and unknowns must be arrays", code="INVALID_ANALYSIS_DATA")
        for item in assumptions:
            if set(item) != {"text", "confidence", "evidence"} if isinstance(item, dict) else True:
                raise PlanAnvilError("Invalid assumption fields", code="INVALID_ANALYSIS_DATA", details=item)
            if item.get("confidence") not in CONFIDENCE or not str(item.get("text", "")).strip():
                raise PlanAnvilError("Invalid assumption", code="INVALID_ANALYSIS_DATA", details=item)
            item_evidence = item.get("evidence", [])
            if not isinstance(item_evidence, list):
                raise PlanAnvilError("Assumption evidence must be an array", code="INVALID_ANALYSIS_DATA")
            item["evidence"] = [_relative_existing(repo, value, code="ANALYSIS_EVIDENCE_MISSING") for value in item_evidence]
        for item in unknowns:
            if set(item) != {"text", "critical", "verification"} if isinstance(item, dict) else True:
                raise PlanAnvilError("Invalid unknown fields", code="INVALID_ANALYSIS_DATA", details=item)
            if (
                not str(item.get("text", "")).strip()
                or not isinstance(item.get("critical"), bool)
                or not str(item.get("verification", "")).strip()
            ):
                raise PlanAnvilError("Invalid unknown", code="INVALID_ANALYSIS_DATA", details=item)

        payload = {
            "schema_version": SCHEMA_VERSION,
            "created_at": utc_now(),
            "goal_hash": sha256_file(run / "evidence/original-goal.md"),
            "markdown_hash": sha256_text(markdown),
            "classification": raw["classification"],
            "risk": raw["risk"],
            "affected_paths": sorted(set(affected)),
            "evidence": sorted(set(evidence)),
            "assumptions": assumptions,
            "unknowns": unknowns,
        }
        schema_path = Path(__file__).resolve().parent.parent / "schemas/analysis.schema.json"
        schema_errors = validate(payload, load_json(schema_path))
        if schema_errors:
            raise PlanAnvilError("Analysis schema validation failed", code="SCHEMA_VALIDATION_FAILED", details=schema_errors)
        json_findings = privacy_findings(Path("evidence/analysis.json"), canonical_json_text(payload))
        if json_findings:
            raise PlanAnvilError("Analysis data contains private or secret data", code="ANALYSIS_PRIVACY", details=json_findings)

        created_md = False
        created_json = False
        try:
            atomic_write_text(target_md, markdown, exclusive=True)
            created_md = True
            atomic_write_json(target_json, payload, exclusive=True)
            created_json = True
            assert_valid_file(target_json, schema_path)

            critical = [item for item in unknowns if item["critical"]]
            transition_state(
                state_path,
                expected_revision=state["revision"],
                new_status="BLOCKED" if critical else "ANALYSIS_READY",
                phase="REPORT_AND_STOP" if critical else "GENERATE_ARTIFACTS",
                next_action_type="NONE" if critical else "AUTHOR_PLAN",
                next_action_target=None if critical else "PLAN.md",
                blocker="BLOCKED_BY_CRITICAL_UNKNOWN" if critical else None,
                hash_paths=[target_md, target_json],
                lock_held=True,
            )
        except Exception:
            if created_json:
                target_json.unlink(missing_ok=True)
            if created_md:
                target_md.unlink(missing_ok=True)
            raise

    critical = [item for item in unknowns if item["critical"]]
    if critical:
        return {
            "ok": False,
            "result": "BLOCKED_BY_CRITICAL_UNKNOWN",
            "analysis": repo_relative(repo, target_json),
            "unknowns": critical,
        }
    return {
        "ok": True,
        "result": "ANALYSIS_READY",
        "analysis": repo_relative(repo, target_json),
        "markdown": repo_relative(repo, target_md),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Record deterministic PlanAnvil goal analysis")
    parser.add_argument("--planning", type=Path, default=Path.cwd())
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--analysis-markdown", type=Path, required=True)
    parser.add_argument("--analysis-data", type=Path, required=True)
    args = parser.parse_args()
    payload = record_analysis(
        args.planning,
        args.run_root,
        analysis_markdown=args.analysis_markdown,
        analysis_data=args.analysis_data,
    )
    return emit(payload, exit_code=0 if payload["ok"] else 2)


if __name__ == "__main__":
    cli_main(main)
