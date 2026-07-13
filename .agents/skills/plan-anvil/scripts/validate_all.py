from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import PlanAnvilError, atomic_write_json, cli_main, discover_repo, emit, load_json, utc_now
from path_safety import assert_safe_run_root
from schema_validator import assert_valid_file
from transition_state import run_lock, transition_state
from validate_artifacts import validate_artifacts
from validate_diff import validate_diff
from validate_path_safety import validate_path_safety
from validate_plan_contract import validate_plan_contract
from validate_profile import validate_profile
from validate_schema_coverage import validate_schema_coverage
from validate_traceability import validate_traceability


def _validate_all_locked(
    repo: Path,
    run: Path,
    *,
    source: Path | None,
    phase: str,
    advance_state: bool,
) -> dict[str, Any]:
    results = {
        "profile": validate_profile(repo),
        "artifacts": validate_artifacts(repo, run, phase=phase, write_report=True),
        "plan": validate_plan_contract(repo, run, write_report=True),
        "path_safety": validate_path_safety(repo, run, write_report=True),
        "traceability": validate_traceability(repo, run, write_report=True),
        "diff": validate_diff(repo, run, source=source, write_report=True),
    }
    results["schema_coverage"] = validate_schema_coverage(repo, run, write_report=True)
    findings = [
        {"validator": name, "findings": result.get("findings", [])}
        for name, result in results.items()
        if not result.get("ok")
    ]
    payload = {
        "schema_version": "1.1.0",
        "generated_at": utc_now(),
        "validator": "validate_all",
        "phase": phase,
        "result": "PASS" if not findings else "FAIL",
        "validators": {name: result.get("result") for name, result in results.items()},
        "findings": findings,
    }
    summary_path = run / "reports/validation/summary.json"
    atomic_write_json(summary_path, payload)
    schema = Path(__file__).resolve().parent.parent / "schemas/validation-report.schema.json"
    assert_valid_file(summary_path, schema)

    if not findings and advance_state and phase == "pre-review":
        state_path = run / "state.json"
        state = load_json(state_path)
        if state["status"] != "ARTIFACTS_GENERATED":
            raise PlanAnvilError(
                f"Deterministic validation requires ARTIFACTS_GENERATED, found {state['status']}",
                code="INVALID_STATE_FOR_VALIDATION",
            )
        transition_state(
            state_path,
            expected_revision=state["revision"],
            new_status="DETERMINISTICALLY_VALID",
            phase="BLIND_PLAN_REVIEW",
            next_action_type="PREPARE_REVIEW_BUNDLE",
            next_action_target="reports/plan-review/review-bundle.json",
            hash_paths=[run / "PLAN.md", run / "traceability.json", summary_path],
            lock_held=True,
        )

    return {"ok": not findings, **payload}


def validate_all(
    planning: Path,
    run_root: Path,
    *,
    source: Path | None = None,
    phase: str = "pre-review",
    advance_state: bool = True,
    lock_held: bool = False,
) -> dict[str, Any]:
    repo = discover_repo(planning)
    run = assert_safe_run_root(repo, run_root)
    state_path = run / "state.json"
    if lock_held:
        return _validate_all_locked(
            repo,
            run,
            source=source,
            phase=phase,
            advance_state=advance_state,
        )
    with run_lock(state_path, command=f"validate-all:{phase}"):
        return _validate_all_locked(
            repo,
            run,
            source=source,
            phase=phase,
            advance_state=advance_state,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all PlanAnvil deterministic validators")
    parser.add_argument("--planning", type=Path, default=Path.cwd())
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--phase", choices=["pre-review", "final"], default="pre-review")
    parser.add_argument("--no-advance-state", action="store_true")
    args = parser.parse_args()
    payload = validate_all(
        args.planning,
        args.run_root,
        source=args.source,
        phase=args.phase,
        advance_state=not args.no_advance_state,
    )
    return emit(payload, exit_code=0 if payload["ok"] else 2)


if __name__ == "__main__":
    cli_main(main)
