from __future__ import annotations

import argparse
import ast
import re
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from common import (
    STAGE_ID_RE,
    TERMINAL_PLAN_STATUSES,
    PlanAnvilError,
    atomic_write_json,
    cli_main,
    discover_repo,
    emit,
    ensure_inside,
    load_json,
    repo_relative,
    utc_now,
)

REQUIRED_PLAN_HEADINGS = [
    "## Identity",
    "## Original goal",
    "## Outcome and definition of done",
    "## Generator stop boundary",
    "## Separate execution-run prompt",
    "## Scope",
    "## Exclusions",
    "## Assumptions, unknowns, and evidence",
    "## Applicable instructions",
    "## System and change analysis",
    "## Dependencies and classification",
    "## Stable stage index",
    "## Traceability",
    "## Testing and independent verification",
    "## Git, integration, and control-root rules",
    "## Production verification, switching, and approvals",
    "## Rollback and recovery",
    "## Resume and reconciliation",
    "## Status and next action",
    "## Final report requirements",
]

REQUIRED_STAGE_HEADINGS = [
    "## Outcome",
    "## Scope",
    "## Exclusions",
    "## Affected paths or discovery procedure",
    "## Applicable instructions",
    "## Dependencies and conflicts",
    "## Acceptance criteria",
    "## Risks and controls",
    "## Evidence cycle",
    "## Modifier and verifier roles",
    "## Commit and checkpoint",
    "## Rollback",
]

REQUIRED_STAGE_METADATA = [
    "outcome",
    "classification",
    "requirements",
    "criteria",
    "risks",
    "dependencies",
    "applicable_instructions",
    "allowed_write_paths",
]

PLACEHOLDER_RE = re.compile(r"\{\{[^}]+\}\}|\b(?:TODO|TBD)\b|\[REPLACE(?: ME)?\]", re.IGNORECASE)
BOUNDARY_VIOLATIONS = [
    re.compile(r"(?is)after (?:creating|generating|validating) (?:the )?plan.{0,120}(?:implement|start jim|execute stage)"),
    re.compile(r"(?i)continue (?:directly )?into implementation"),
    re.compile(r"(?i)immediately start jim"),
    re.compile(r"(?i)in this (?:same )?run.{0,80}(?:implement|execute|modify product)"),
]
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise PlanAnvilError(f"Missing stage frontmatter: {path.name}", code="STAGE_FRONTMATTER_MISSING")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise PlanAnvilError(f"Unclosed stage frontmatter: {path.name}", code="STAGE_FRONTMATTER_INVALID")
    data: dict[str, Any] = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise PlanAnvilError(f"Invalid stage frontmatter line in {path.name}: {line}", code="STAGE_FRONTMATTER_INVALID")
        key, raw = line.split(":", 1)
        key = key.strip()
        if not key or key in data:
            raise PlanAnvilError(f"Duplicate or empty stage metadata key in {path.name}: {key}", code="STAGE_FRONTMATTER_INVALID")
        raw = raw.strip()
        if not raw:
            data[key] = None
            continue
        try:
            data[key] = ast.literal_eval(raw)
        except (SyntaxError, ValueError):
            data[key] = raw.strip("\"'")
    return data


def _section(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    body_start = start + len(heading)
    next_heading = re.search(r"(?m)^##\s+", text[body_start:])
    end = body_start + next_heading.start() if next_heading else len(text)
    return text[body_start:end].strip()


def _duplicates(values: list[Any]) -> list[Any]:
    return sorted(value for value, count in Counter(values).items() if value is not None and count > 1)


def _safe_relative_glob(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        return False
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or WINDOWS_ABSOLUTE_RE.match(value) or normalized.startswith("//"):
        return False
    parts = PurePosixPath(normalized).parts
    return ".." not in parts and ".git" not in parts


def _dependency_cycles(stages: dict[str, dict[str, Any]]) -> list[list[str]]:
    cycles: list[list[str]] = []
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(stage_id: str) -> None:
        if stage_id in visiting:
            index = visiting.index(stage_id)
            cycle = visiting[index:] + [stage_id]
            if cycle not in cycles:
                cycles.append(cycle)
            return
        if stage_id in visited:
            return
        visiting.append(stage_id)
        for dependency in stages.get(stage_id, {}).get("dependencies") or []:
            if dependency in stages:
                visit(dependency)
        visiting.pop()
        visited.add(stage_id)

    for stage_id in stages:
        visit(stage_id)
    return cycles


def _load_risks(run: Path, findings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    risks: dict[str, dict[str, Any]] = {}
    for path in sorted((run / "risks").glob("RISK-*.json")):
        try:
            risk = load_json(path)
        except PlanAnvilError as exc:
            findings.append({"kind": exc.code, "path": f"risks/{path.name}", "message": str(exc)})
            continue
        risk_id = risk.get("id")
        if not isinstance(risk_id, str):
            findings.append({"kind": "risk-id-missing", "path": f"risks/{path.name}"})
            continue
        if path.stem != risk_id:
            findings.append({"kind": "risk-filename-mismatch", "path": f"risks/{path.name}", "risk": risk_id})
        if risk_id in risks:
            findings.append({"kind": "duplicate-risk-id", "risk": risk_id})
        risks[risk_id] = risk
    return risks


def validate_plan(planning: Path, run_root: Path, *, write_report: bool = True) -> dict[str, Any]:
    repo = discover_repo(planning)
    run = ensure_inside(repo, run_root if run_root.is_absolute() else repo / run_root)
    plan_path = run / "PLAN.md"
    findings: list[dict[str, Any]] = []
    plan_status: str | None = None
    manifest = load_json(run / "manifest.json") if (run / "manifest.json").is_file() else {}
    instruction_map = load_json(run / "evidence/instruction-map.json") if (run / "evidence/instruction-map.json").is_file() else None
    instruction_hashes = {
        item.get("path"): item.get("sha256")
        for item in (instruction_map or {}).get("files", [])
        if isinstance(item, dict)
    }

    if not plan_path.is_file():
        findings.append({"kind": "missing", "path": repo_relative(repo, plan_path)})
        plan_text = ""
    else:
        plan_text = plan_path.read_text(encoding="utf-8")
        for heading in REQUIRED_PLAN_HEADINGS:
            if heading not in plan_text:
                findings.append({"kind": "missing-heading", "path": "PLAN.md", "heading": heading})
        for match in PLACEHOLDER_RE.finditer(plan_text):
            findings.append({"kind": "placeholder", "path": "PLAN.md", "value": match.group(0)})
        for pattern in BOUNDARY_VIOLATIONS:
            if pattern.search(plan_text):
                findings.append({"kind": "generator-executor-boundary-violation", "path": "PLAN.md"})
                break
        required_stop = "No implementation was executed. Start a separate Codex run using the execution prompt in PLAN.md."
        if required_stop not in plan_text:
            findings.append({"kind": "missing-hard-stop-statement", "path": "PLAN.md"})

        if manifest:
            expected_identity = {
                "Plan ID": manifest.get("plan_id"),
                "Run ID": manifest.get("run_id"),
                "Base branch": manifest.get("repository", {}).get("base_branch"),
                "Base SHA": manifest.get("repository", {}).get("base_sha"),
                "Planning branch": manifest.get("repository", {}).get("planning_branch"),
            }
            for label, value in expected_identity.items():
                if value is not None and f"- {label}: `{value}`" not in plan_text:
                    findings.append({"kind": "plan-identity-mismatch", "field": label, "expected": value})

        statuses = re.findall(r"(?m)^- Status:\s*`([^`]+)`\s*$", plan_text)
        if len(statuses) != 1:
            findings.append({"kind": "plan-status-count", "count": len(statuses)})
            plan_status = None
        else:
            plan_status = statuses[0]
            if plan_status not in TERMINAL_PLAN_STATUSES:
                findings.append({"kind": "invalid-plan-status", "status": plan_status})
        next_actions = [item.strip() for item in re.findall(r"(?m)^- Next action:\s*`([^`]+)`\s*$", plan_text)]
        if len(next_actions) != 1 or not next_actions[0]:
            findings.append({"kind": "plan-next-action-count", "count": len(next_actions)})

    trace = load_json(run / "traceability.json") if (run / "traceability.json").is_file() else {
        "requirements": [], "criteria": [], "controls": [], "gaps": []
    }
    stage_paths = sorted((run / "stages").glob("STAGE-*.md"))
    stages: dict[str, dict[str, Any]] = {}

    for path in stage_paths:
        text = path.read_text(encoding="utf-8")
        try:
            metadata = _frontmatter(path)
        except PlanAnvilError as exc:
            findings.append({"kind": exc.code, "path": path.name, "message": str(exc)})
            continue
        stage_id = metadata.get("stage_id")
        if not isinstance(stage_id, str) or not STAGE_ID_RE.fullmatch(stage_id):
            findings.append({"kind": "invalid-stage-id", "path": path.name, "value": stage_id})
            continue
        if path.stem != stage_id:
            findings.append({"kind": "stage-filename-mismatch", "path": path.name, "stage_id": stage_id})
        if stage_id in stages:
            findings.append({"kind": "duplicate-stage-id", "stage_id": stage_id})
        stages[stage_id] = metadata
        if metadata.get("schema_version") != "1.1.0":
            findings.append({"kind": "stage-schema-version", "path": path.name})
        for key in REQUIRED_STAGE_METADATA:
            if key not in metadata:
                findings.append({"kind": "stage-metadata-missing", "path": path.name, "field": key})
        if not isinstance(metadata.get("outcome"), str) or not metadata.get("outcome", "").strip():
            findings.append({"kind": "stage-outcome-invalid", "stage": stage_id})
        if not isinstance(metadata.get("classification"), str) or not metadata.get("classification", "").strip():
            findings.append({"kind": "stage-classification-invalid", "stage": stage_id})
        for field in ["requirements", "criteria", "risks", "dependencies", "applicable_instructions", "allowed_write_paths"]:
            if field in metadata and not isinstance(metadata[field], list):
                findings.append({"kind": "stage-metadata-type", "stage": stage_id, "field": field, "expected": "list"})
        for allowed_path in metadata.get("allowed_write_paths") or []:
            if not _safe_relative_glob(allowed_path):
                findings.append({"kind": "unsafe-stage-write-path", "stage": stage_id, "path": allowed_path})
        instruction_refs = metadata.get("applicable_instructions") or []
        if instruction_hashes and not instruction_refs:
            findings.append({"kind": "stage-without-applicable-instructions", "stage": stage_id})
        for reference in instruction_refs:
            if not isinstance(reference, dict) or set(reference) != {"path", "sha256"}:
                findings.append({"kind": "invalid-stage-instruction-reference", "stage": stage_id, "reference": reference})
                continue
            ref_path = reference.get("path")
            ref_hash = reference.get("sha256")
            if not _safe_relative_glob(ref_path) or not isinstance(ref_hash, str) or not HASH_RE.fullmatch(ref_hash):
                findings.append({"kind": "invalid-stage-instruction-reference", "stage": stage_id, "reference": reference})
            elif instruction_hashes.get(ref_path) != ref_hash:
                findings.append({"kind": "stale-or-unmapped-instruction-reference", "stage": stage_id, "path": ref_path})
        for heading in REQUIRED_STAGE_HEADINGS:
            if heading not in text:
                findings.append({"kind": "missing-heading", "path": path.name, "heading": heading})
        for match in PLACEHOLDER_RE.finditer(text):
            findings.append({"kind": "placeholder", "path": path.name, "value": match.group(0)})
        evidence = _section(text, "## Evidence cycle").upper()
        for marker in ["GREEN", "RED", "IMPLEMENT", "INDEPENDENT"]:
            if marker not in evidence:
                findings.append({"kind": "stage-evidence-cycle-incomplete", "stage": stage_id, "missing": marker})
        if not _section(text, "## Rollback"):
            findings.append({"kind": "stage-rollback-empty", "stage": stage_id})
        commit_section = _section(text, "## Commit and checkpoint").lower()
        if "commit" not in commit_section or "checkpoint" not in commit_section:
            findings.append({"kind": "stage-commit-checkpoint-incomplete", "stage": stage_id})

    ready = plan_status == "PLAN_READY"
    if ready and not stages:
        findings.append({"kind": "ready-plan-without-stages"})

    requirements = trace.get("requirements", [])
    criteria = trace.get("criteria", [])
    controls = trace.get("controls", [])
    requirement_ids_list = [item.get("id") for item in requirements]
    criterion_ids_list = [item.get("id") for item in criteria]
    control_ids_list = [item.get("id") for item in controls]
    for duplicate in _duplicates(requirement_ids_list):
        findings.append({"kind": "duplicate-requirement-id", "id": duplicate})
    for duplicate in _duplicates(criterion_ids_list):
        findings.append({"kind": "duplicate-criterion-id", "id": duplicate})
    for duplicate in _duplicates(control_ids_list):
        findings.append({"kind": "duplicate-control-id", "id": duplicate})
    requirement_ids = set(requirement_ids_list)
    criterion_ids = set(criterion_ids_list)
    control_ids = set(control_ids_list)
    criteria_by_stage: dict[str, set[str]] = {}
    requirements_by_stage: dict[str, set[str]] = {}

    for requirement in requirements:
        req_id = requirement.get("id")
        for stage_id in requirement.get("stages", []):
            requirements_by_stage.setdefault(stage_id, set()).add(req_id)
            if stage_id not in stages:
                findings.append({"kind": "traceability-missing-stage", "requirement": req_id, "stage": stage_id})
        for criterion in requirement.get("criteria", []):
            if criterion not in criterion_ids:
                findings.append({"kind": "traceability-missing-criterion", "requirement": req_id, "criterion": criterion})

    referenced_risks: set[str] = set()
    referenced_controls: set[str] = set()
    for criterion in criteria:
        criterion_id = criterion.get("id")
        stage_id = criterion.get("stage")
        criteria_by_stage.setdefault(stage_id, set()).add(criterion_id)
        if stage_id not in stages:
            findings.append({"kind": "criterion-stage-missing", "criterion": criterion_id, "stage": stage_id})
        if not criterion.get("controls"):
            findings.append({"kind": "criterion-without-control", "criterion": criterion_id})
        if not criterion.get("evidence_type"):
            findings.append({"kind": "criterion-without-evidence", "criterion": criterion_id})
        for control in criterion.get("controls", []):
            referenced_controls.add(control)
            if control not in control_ids:
                findings.append({"kind": "criterion-control-missing", "criterion": criterion_id, "control": control})
        referenced_risks.update(criterion.get("risks", []))

    for stage_id, metadata in stages.items():
        stage_requirements = set(metadata.get("requirements") or [])
        stage_criteria = set(metadata.get("criteria") or [])
        stage_risks = set(metadata.get("risks") or [])
        if ready and not stage_requirements:
            findings.append({"kind": "stage-without-requirement", "stage": stage_id})
        if ready and not stage_criteria:
            findings.append({"kind": "stage-without-criterion", "stage": stage_id})
        for dependency in metadata.get("dependencies") or []:
            if dependency == stage_id or dependency not in stages:
                findings.append({"kind": "invalid-stage-dependency", "stage": stage_id, "dependency": dependency})
        for requirement in stage_requirements:
            if requirement not in requirement_ids:
                findings.append({"kind": "stage-requirement-missing", "stage": stage_id, "requirement": requirement})
        for criterion in stage_criteria:
            if criterion not in criterion_ids:
                findings.append({"kind": "stage-criterion-missing", "stage": stage_id, "criterion": criterion})
        if stage_requirements != requirements_by_stage.get(stage_id, set()):
            findings.append({"kind": "stage-requirement-link-mismatch", "stage": stage_id})
        if stage_criteria != criteria_by_stage.get(stage_id, set()):
            findings.append({"kind": "stage-criterion-link-mismatch", "stage": stage_id})
        criterion_risks = {
            risk
            for criterion in criteria
            if criterion.get("stage") == stage_id
            for risk in criterion.get("risks", [])
        }
        if stage_risks != criterion_risks:
            findings.append({"kind": "stage-risk-link-mismatch", "stage": stage_id})

    for cycle in _dependency_cycles(stages):
        findings.append({"kind": "stage-dependency-cycle", "cycle": cycle})

    risks = _load_risks(run, findings)
    for risk_id in sorted(referenced_risks - set(risks)):
        findings.append({"kind": "missing-risk-file", "risk": risk_id})
    for risk_id, risk in risks.items():
        stage_id = risk.get("stage")
        if stage_id not in stages:
            findings.append({"kind": "risk-stage-missing", "risk": risk_id, "stage": stage_id})
        if risk_id not in referenced_risks:
            findings.append({"kind": "unreferenced-risk", "risk": risk_id})
        for criterion in risk.get("criteria", []):
            if criterion not in criterion_ids:
                findings.append({"kind": "risk-criterion-missing", "risk": risk_id, "criterion": criterion})
        for control in [*risk.get("controls", []), *risk.get("detection", [])]:
            referenced_controls.add(control)
            if control not in control_ids:
                findings.append({"kind": "risk-control-missing", "risk": risk_id, "control": control})
        if not str(risk.get("mitigation", "")).strip() or not str(risk.get("rollback", "")).strip():
            findings.append({"kind": "risk-response-incomplete", "risk": risk_id})

    for control in sorted(control_ids - referenced_controls):
        findings.append({"kind": "control-without-behavior", "control": control})
    for gap in trace.get("gaps", []):
        if gap.get("critical"):
            findings.append({"kind": "critical-traceability-gap", "gap": gap})

    if ready and not requirements:
        findings.append({"kind": "ready-plan-without-requirements"})
    if ready and not criteria:
        findings.append({"kind": "ready-plan-without-criteria"})

    payload = {
        "schema_version": "1.1.0",
        "generated_at": utc_now(),
        "validator": "validate_plan",
        "result": "PASS" if not findings else "FAIL",
        "findings": findings,
        "plan_status": plan_status,
        "stage_ids": sorted(stages),
        "requirement_count": len(requirement_ids),
        "criterion_count": len(criterion_ids),
        "control_count": len(control_ids),
        "risk_count": len(risks),
    }
    if write_report:
        atomic_write_json(run / "reports/validation/plan.json", payload)
    return {"ok": not findings, **payload}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate PlanAnvil PLAN.md, stages, identifiers, and traceability")
    parser.add_argument("--planning", type=Path, default=Path.cwd())
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--no-write-report", action="store_true")
    args = parser.parse_args()
    payload = validate_plan(args.planning, args.run_root, write_report=not args.no_write_report)
    return emit(payload, exit_code=0 if payload["ok"] else 2)


if __name__ == "__main__":
    cli_main(main)
