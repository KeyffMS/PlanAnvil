from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import atomic_write_json, canonical_file_is_valid, cli_main, discover_repo, emit, utc_now
from path_safety import assert_safe_run_root
from schema_validator import validate_file

_EXACT_SCHEMAS = {
    "manifest.json": "manifest.schema.json",
    "state.json": "state.schema.json",
    "compliance.json": "compliance.schema.json",
    "traceability.json": "traceability.schema.json",
    "evidence/git-capability.json": "git-capability.schema.json",
    "evidence/lifecycle.json": "lifecycle.schema.json",
    "evidence/instruction-map.json": "instruction-map.schema.json",
    "evidence/analysis.json": "analysis.schema.json",
    "reports/plan-review/review-bundle.json": "review-bundle.schema.json",
    "reports/plan-review/blind-review.json": "review.schema.json",
    "reports/plan-review/comparison.json": "comparison.schema.json",
    "reports/validation/artifacts.json": "validation-report.schema.json",
    "reports/validation/plan.json": "validation-report.schema.json",
    "reports/validation/diff.json": "validation-report.schema.json",
    "reports/validation/path-safety.json": "validation-report.schema.json",
    "reports/validation/traceability.json": "validation-report.schema.json",
    "reports/validation/schema-coverage.json": "validation-report.schema.json",
    "reports/validation/summary.json": "validation-report.schema.json",
}


def _schema_for(relative: str) -> str | None:
    if relative in _EXACT_SCHEMAS:
        return _EXACT_SCHEMAS[relative]
    path = Path(relative)
    if path.parent.as_posix() == "risks" and path.name.startswith("RISK-"):
        return "risk.schema.json"
    if path.parent.as_posix() == "checkpoints" and path.name.startswith("CHECKPOINT-"):
        return "checkpoint.schema.json"
    return None


def validate_schema_coverage(planning: Path, run_root: Path, *, write_report: bool = True) -> dict[str, Any]:
    repo = discover_repo(planning)
    run = assert_safe_run_root(repo, run_root)
    schemas = Path(__file__).resolve().parent.parent / "schemas"
    findings: list[dict[str, Any]] = []
    validated: list[str] = []

    for path in sorted(run.rglob("*.json")):
        relative = path.relative_to(run).as_posix()
        if relative == "local-state.json" or any(part.startswith(".") for part in path.relative_to(run).parts):
            continue
        schema_name = _schema_for(relative)
        if schema_name is None:
            findings.append({"kind": "missing-versioned-schema", "path": relative})
            continue
        schema_path = schemas / schema_name
        if not schema_path.is_file():
            findings.append({"kind": "schema-file-missing", "path": relative, "schema": schema_name})
            continue
        errors = validate_file(path, schema_path)
        if errors:
            findings.append({"kind": "schema", "path": relative, "schema": schema_name, "errors": errors})
            continue
        if not canonical_file_is_valid(path):
            findings.append({"kind": "non-canonical-json", "path": relative})
            continue
        validated.append(relative)

    payload = {
        "schema_version": "1.1.0",
        "generated_at": utc_now(),
        "validator": "validate_schema_coverage",
        "result": "PASS" if not findings else "FAIL",
        "findings": findings,
        "validated": validated,
    }
    if write_report:
        atomic_write_json(run / "reports/validation/schema-coverage.json", payload)
    return {"ok": not findings, **payload}


def main() -> int:
    parser = argparse.ArgumentParser(description="Require a versioned schema for every committed JSON artifact")
    parser.add_argument("--planning", type=Path, default=Path.cwd())
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--no-write-report", action="store_true")
    args = parser.parse_args()
    payload = validate_schema_coverage(args.planning, args.run_root, write_report=not args.no_write_report)
    return emit(payload, exit_code=0 if payload["ok"] else 2)


if __name__ == "__main__":
    cli_main(main)
