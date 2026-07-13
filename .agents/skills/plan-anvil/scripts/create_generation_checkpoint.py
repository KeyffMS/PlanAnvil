from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import (
    PlanAnvilError,
    SCHEMA_VERSION,
    atomic_write_json,
    canonical_json_text,
    cli_main,
    discover_repo,
    emit,
    git,
    load_json,
    repo_relative,
    sha256_file,
    utc_now,
)
from schema_validator import assert_valid_file, validate
from transition_state import run_lock


def _existing_hashes(repo: Path, run: Path, state: dict[str, Any]) -> dict[str, str]:
    retained: dict[str, str] = {}
    for relative, expected in state.get("artifact_hashes", {}).items():
        candidates = [run / relative, repo / relative, run / Path(relative).name]
        existing = next((path for path in candidates if path.is_file()), None)
        if existing is not None and sha256_file(existing) == expected:
            retained[relative] = expected
    return retained


def _checkpoint_id(revision: int) -> str:
    return f"CHECKPOINT-00-GENERATION_R{revision:04d}"


def create_generation_checkpoint(planning: Path, run_root: Path) -> dict[str, Any]:
    repo = discover_repo(planning)
    run = (run_root if run_root.is_absolute() else repo / run_root).resolve()
    try:
        run.relative_to(repo)
    except ValueError as exc:
        raise PlanAnvilError("Run root escapes planning worktree", code="PATH_ESCAPE") from exc
    state_path = run / "state.json"

    with run_lock(state_path, command="create-generation-checkpoint"):
        state_schema = Path(__file__).resolve().parent.parent / "schemas/state.schema.json"
        checkpoint_schema = Path(__file__).resolve().parent.parent / "schemas/checkpoint.schema.json"
        assert_valid_file(state_path, state_schema)
        state = load_json(state_path)
        if state.get("mode") != "PLAN_GENERATION":
            raise PlanAnvilError(
                "Generation checkpoint command requires PLAN_GENERATION mode",
                code="INVALID_CHECKPOINT_MODE",
            )

        existing_relative = state.get("last_checkpoint")
        if isinstance(existing_relative, str) and existing_relative:
            existing_path = run / existing_relative
            expected = state.get("artifact_hashes", {}).get(existing_relative)
            if existing_path.is_file() and expected == sha256_file(existing_path):
                errors = validate(load_json(existing_path), load_json(checkpoint_schema))
                if not errors:
                    return {
                        "ok": True,
                        "result": "CHECKPOINT_ALREADY_VALID",
                        "checkpoint": repo_relative(repo, existing_path),
                    }

        branch = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip()
        head = git(repo, "rev-parse", "HEAD").stdout.strip()
        checkpoint_id = _checkpoint_id(state["revision"])
        relative = f"checkpoints/{checkpoint_id}.json"
        checkpoint_path = run / relative
        summary_relative = "reports/validation/summary.json"
        tests_evidence = [summary_relative] if (run / summary_relative).is_file() else []
        diff_relative = "reports/validation/diff.json"
        write_evidence = [diff_relative] if (run / diff_relative).is_file() else []

        checkpoint = {
            "schema_version": SCHEMA_VERSION,
            "id": checkpoint_id,
            "created_at": utc_now(),
            "mode": "PLAN_GENERATION",
            "stage": state.get("current_stage"),
            "phase": state.get("current_phase") or "UNKNOWN",
            "result": "PASS",
            "git": {
                "branch": branch,
                "head": head,
                "worktree_role": "PLANNING",
                "status": "DIRTY",
            },
            "tests": {
                "summary": "Generation recovery checkpoint; testing status is preserved in referenced validation evidence when available.",
                "evidence": tests_evidence,
            },
            "risks": {"open": [], "closed": []},
            "agent_tree": {"status": "COMPLIANT", "evidence": []},
            "write_scope": {"status": "COMPLIANT", "evidence": write_evidence},
            "next_action": state["next_action"],
            "recovery": [
                "Read manifest.json, state.json, local-state.json and this checkpoint.",
                "Verify the recorded planning branch, HEAD, worktree status and artifact hashes.",
                "Continue only with the recorded next action after reconciliation.",
            ],
            "artifact_hashes": _existing_hashes(repo, run, state),
        }
        checkpoint_errors = validate(checkpoint, load_json(checkpoint_schema))
        if checkpoint_errors:
            raise PlanAnvilError(
                "Generation checkpoint failed schema validation",
                code="SCHEMA_VALIDATION_FAILED",
                details=checkpoint_errors,
            )
        atomic_write_json(checkpoint_path, checkpoint, exclusive=True)
        assert_valid_file(checkpoint_path, checkpoint_schema)

        replacement = {
            **state,
            "revision": state["revision"] + 1,
            "updated_at": utc_now(),
            "last_checkpoint": relative,
            "artifact_hashes": {
                **state.get("artifact_hashes", {}),
                relative: sha256_file(checkpoint_path),
            },
        }
        state_errors = validate(replacement, load_json(state_schema))
        if state_errors:
            raise PlanAnvilError(
                "Checkpoint state update failed schema validation",
                code="SCHEMA_VALIDATION_FAILED",
                details=state_errors,
            )
        atomic_write_json(state_path, replacement)
        assert_valid_file(state_path, state_schema)

    return {
        "ok": True,
        "result": "GENERATION_CHECKPOINT_READY",
        "checkpoint": repo_relative(repo, checkpoint_path),
        "state_revision": replacement["revision"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a durable PlanAnvil generation checkpoint before compaction")
    parser.add_argument("--planning", type=Path, default=Path.cwd())
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    return emit(create_generation_checkpoint(args.planning, args.run_root))


if __name__ == "__main__":
    cli_main(main)
