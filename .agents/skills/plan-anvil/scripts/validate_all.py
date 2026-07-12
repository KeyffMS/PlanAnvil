from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import PlanAnvilError, atomic_write_json, cli_main, discover_repo, emit, load_json, utc_now
from transition_state import transition_state
from validate_artifacts import validate_artifacts
from validate_diff import validate_diff
from validate_plan import validate_plan
from validate_profile import validate_profile


def validate_all(
    planning: Path,
    run_root: Path,
    *,
    source: Path | None = None,
    phase: str = "pre-review",
    advance_state: bool = True,
) -> dict[str, Any]:
    repo = discover_repo(planning)
    run = (run_root if run_root.is_absolute() else repo / run_root).resolve()

    results = {
        "profile": validate_profile(repo),
        "artifacts": validate_artifacts(repo, run, phase=phase, write_report=True),
        "plan": validate_plan(repo, run, write_report=True),
        "diff": validate_diff(repo, run, source=source, write_report=True),
    }
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
    atomic_write_json(run / "reports/validation/summary.json", payload)

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
            hash_paths=[run / "PLAN.md", run / "traceability.json", run / "reports/validation/summary.json"],
        )

    return {"ok": not findings, **payload}


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
