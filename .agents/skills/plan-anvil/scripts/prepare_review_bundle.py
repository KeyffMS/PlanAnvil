from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import (
    PlanAnvilError,
    atomic_write_json,
    atomic_write_text,
    cli_main,
    discover_repo,
    emit,
    load_json,
    repo_relative,
    sha256_file,
    utc_now,
)
from transition_state import run_lock


def review_candidates(repo: Path, run: Path) -> list[Path]:
    return [
        repo / ".pursue/SYSTEM_PROFILE.md",
        run / "evidence/original-goal.md",
        run / "evidence/git-capability.json",
        run / "evidence/lifecycle.json",
        run / "evidence/instruction-map.json",
        run / "evidence/analysis.md",
        run / "evidence/analysis.json",
        run / "PLAN.md",
        run / "traceability.json",
        run / "reports/validation/summary.json",
        *sorted((run / "stages").glob("STAGE-*.md")),
        *sorted((run / "risks").glob("RISK-*.json")),
    ]


def review_file_entries(repo: Path, run: Path) -> list[dict[str, str]]:
    candidates = review_candidates(repo, run)
    missing = [repo_relative(repo, path) for path in candidates if not path.is_file()]
    if missing:
        raise PlanAnvilError("Review bundle inputs are missing", code="REVIEW_INPUT_MISSING", details=missing)
    return [
        {
            "path": repo_relative(repo, path),
            "sha256": sha256_file(path),
            "role": (
                "goal" if path.name == "original-goal.md"
                else "git-capability" if path.name == "git-capability.json"
                else "lifecycle" if path.name == "lifecycle.json"
                else "profile" if path.name == "SYSTEM_PROFILE.md"
                else "instruction-map" if path.name == "instruction-map.json"
                else "analysis" if path.name in {"analysis.md", "analysis.json"}
                else "plan" if path.name == "PLAN.md"
                else "traceability" if path.name == "traceability.json"
                else "deterministic-validation" if path.name == "summary.json"
                else "stage" if path.parent.name == "stages"
                else "risk"
            ),
        }
        for path in candidates
    ]


def prepare_review_bundle(planning: Path, run_root: Path) -> dict[str, Any]:
    repo = discover_repo(planning)
    run = (run_root if run_root.is_absolute() else repo / run_root).resolve()
    state_path = run / "state.json"
    bundle_path = run / "reports/plan-review/review-bundle.json"
    prompt_path = run / "reports/plan-review/review-prompt.md"

    with run_lock(state_path, command="prepare-review-bundle"):
        state = load_json(state_path)
        if state.get("status") != "DETERMINISTICALLY_VALID":
            raise PlanAnvilError(
                f"Blind review requires DETERMINISTICALLY_VALID, found {state.get('status')}",
                code="INVALID_STATE_FOR_REVIEW",
            )

        summary = load_json(run / "reports/validation/summary.json")
        if summary.get("result") != "PASS":
            raise PlanAnvilError("Deterministic validation did not pass", code="VALIDATION_NOT_PASSED")

        files = review_file_entries(repo, run)
        bundle = {
            "schema_version": "1.1.0",
            "created_at": utc_now(),
            "purpose": "BLIND_PLAN_REVIEW",
            "excludes": ["planner reasoning", "self-review", "conversation transcript", "local-state.json", "SYSTEM_PROFILE.local.md"],
            "files": files,
        }
        prompt = """# Blind Plan Review Brief

Review only the files listed in `review-bundle.json`. Do not request or use planner reasoning, self-review, conversation history, local-state.json, or the local profile.

Assess:

- goal coverage and definition of done;
- unsupported assumptions and critical unknowns;
- instruction compliance;
- stage atomicity and stable identifiers;
- requirement, criterion, risk, control, test, and evidence traceability;
- test strategy and independent verification;
- Git/worktree ownership and approval gates;
- stateful migration, live-switch, rollback, and recovery safety;
- generator/executor separation;
- placeholders, contradictions, and unverifiable commands.

Return a Markdown report using the blind-review template and a structured findings JSON array. Use `PASS` only when no high or critical defect blocks readiness. Do not modify any plan artifact.
"""

        created_bundle = False
        created_prompt = False
        try:
            atomic_write_json(bundle_path, bundle, exclusive=True)
            created_bundle = True
            atomic_write_text(prompt_path, prompt, exclusive=True)
            created_prompt = True
        except Exception:
            if created_prompt:
                prompt_path.unlink(missing_ok=True)
            if created_bundle:
                bundle_path.unlink(missing_ok=True)
            raise

    return {
        "ok": True,
        "result": "REVIEW_BUNDLE_READY",
        "bundle": repo_relative(repo, bundle_path),
        "prompt": repo_relative(repo, prompt_path),
        "files": len(files),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the immutable-input PlanAnvil blind-review bundle")
    parser.add_argument("--planning", type=Path, default=Path.cwd())
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    return emit(prepare_review_bundle(args.planning, args.run_root))


if __name__ == "__main__":
    cli_main(main)
