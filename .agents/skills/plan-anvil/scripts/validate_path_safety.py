from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import PlanAnvilError, atomic_write_json, cli_main, discover_repo, emit, load_json, repo_relative, utc_now
from path_safety import assert_safe_relative_glob, assert_safe_repo_path
from validate_plan import _frontmatter


def validate_path_safety(
    planning: Path,
    run_root: Path,
    *,
    write_report: bool = True,
) -> dict[str, Any]:
    repo = discover_repo(planning)
    run = assert_safe_repo_path(repo, run_root if run_root.is_absolute() else repo / run_root)
    findings: list[dict[str, Any]] = []

    instruction_map_path = run / "evidence/instruction-map.json"
    if instruction_map_path.is_file():
        instruction_map = load_json(instruction_map_path)
        for affected in instruction_map.get("affected_paths", []):
            try:
                assert_safe_repo_path(repo, Path(affected))
            except PlanAnvilError as exc:
                findings.append(
                    {
                        "kind": exc.code,
                        "source": "instruction-map",
                        "path": affected,
                        "message": str(exc),
                    }
                )

    for stage_path in sorted((run / "stages").glob("STAGE-*.md")):
        try:
            metadata = _frontmatter(stage_path)
        except PlanAnvilError as exc:
            findings.append(
                {
                    "kind": exc.code,
                    "source": "stage",
                    "path": repo_relative(repo, stage_path),
                    "message": str(exc),
                }
            )
            continue
        stage_id = metadata.get("stage_id") or stage_path.stem
        for scope in metadata.get("allowed_write_paths") or []:
            try:
                assert_safe_relative_glob(repo, scope)
            except PlanAnvilError as exc:
                findings.append(
                    {
                        "kind": exc.code,
                        "source": "stage-write-scope",
                        "stage": stage_id,
                        "path": scope,
                        "message": str(exc),
                        "details": exc.details,
                    }
                )

    payload = {
        "schema_version": "1.1.0",
        "generated_at": utc_now(),
        "validator": "validate_path_safety",
        "result": "PASS" if not findings else "FAIL",
        "findings": findings,
    }
    if write_report:
        atomic_write_json(run / "reports/validation/path-safety.json", payload)
    return {"ok": not findings, **payload}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate PlanAnvil paths against Git metadata and submodule boundaries")
    parser.add_argument("--planning", type=Path, default=Path.cwd())
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--no-write-report", action="store_true")
    args = parser.parse_args()
    payload = validate_path_safety(
        args.planning,
        args.run_root,
        write_report=not args.no_write_report,
    )
    return emit(payload, exit_code=0 if payload["ok"] else 2)


if __name__ == "__main__":
    cli_main(main)
