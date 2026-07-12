from __future__ import annotations

import argparse
import os
import re
import tomllib
from pathlib import Path
from typing import Any

from common import (
    PlanAnvilError,
    SCHEMA_VERSION,
    atomic_write_json,
    cli_main,
    discover_repo,
    emit,
    ensure_inside,
    load_json,
    repo_relative,
    sha256_bytes,
    utc_now,
)
from schema_validator import assert_valid_file
from transition_state import transition_state


SAFETY_TERMS = re.compile(
    r"(?i)\b(?:must not|never|forbidden|secret|credential|production|deploy|destructive|irreversible|security|privacy|legal|permission|protected branch|data loss)\b"
)


def _load_codex_instruction_config(repo: Path) -> tuple[list[str], int]:
    fallback: list[str] = []
    max_bytes = 32768
    candidates: list[Path] = []
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    candidates.append(codex_home / "config.toml")
    candidates.append(repo / ".codex/config.toml")
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        names = data.get("project_doc_fallback_filenames")
        if isinstance(names, list) and all(isinstance(item, str) and item for item in names):
            fallback = list(dict.fromkeys(names))
        value = data.get("project_doc_max_bytes")
        if isinstance(value, int) and value > 0:
            max_bytes = value
    return fallback, max_bytes


def _scope_directories(repo: Path, affected: str) -> list[Path]:
    raw = Path(affected)
    candidate = raw if raw.is_absolute() else repo / raw
    candidate = ensure_inside(repo, candidate)
    target_dir = candidate if candidate.is_dir() else candidate.parent
    dirs: list[Path] = []
    current = target_dir
    while True:
        dirs.append(current)
        if current == repo:
            break
        current = current.parent
    dirs.reverse()
    return dirs


def _selected_instruction(directory: Path, fallback: list[str]) -> Path | None:
    for name in ["AGENTS.override.md", "AGENTS.md", *fallback]:
        path = directory / name
        if path.is_file() and path.stat().st_size > 0:
            return path
    return None


def map_instructions(
    planning: Path,
    *,
    affected_paths: list[str],
    output: Path,
    fallback_filenames: list[str] | None = None,
    automatic_byte_limit: int | None = None,
    conflicts_file: Path | None = None,
) -> dict[str, Any]:
    repo = discover_repo(planning)
    if not affected_paths:
        affected_paths = ["."]
    configured_fallback, configured_limit = _load_codex_instruction_config(repo)
    fallback = list(dict.fromkeys(fallback_filenames if fallback_filenames is not None else configured_fallback))
    byte_limit = automatic_byte_limit or configured_limit

    normalized_affected: list[str] = []
    selections: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for affected in affected_paths:
        candidate = Path(affected)
        absolute = candidate if candidate.is_absolute() else repo / candidate
        absolute = ensure_inside(repo, absolute)
        relative = repo_relative(repo, absolute)
        normalized_affected.append(relative)
        for precedence, directory in enumerate(_scope_directories(repo, relative)):
            selected = _selected_instruction(directory, fallback)
            if selected is None:
                continue
            key = selected.resolve().as_posix()
            if key not in selections:
                data = selected.read_bytes()
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise PlanAnvilError(
                        f"Instruction file is not UTF-8: {repo_relative(repo, selected)}",
                        code="INSTRUCTION_NOT_UTF8",
                    ) from exc
                safety_rules = []
                for number, line in enumerate(text.splitlines(), start=1):
                    if SAFETY_TERMS.search(line):
                        safety_rules.append(f"L{number} {sha256_bytes(line.encode('utf-8'))}")
                selections[key] = {
                    "path": repo_relative(repo, selected),
                    "sha256": sha256_bytes(data),
                    "bytes": len(data),
                    "full_read": True,
                    "scope": repo_relative(repo, directory),
                    "precedence": precedence,
                    "affected_paths": [],
                    "truncation_risk": False,
                    "safety_critical_rules": safety_rules,
                }
                order.append(key)
            entry = selections[key]
            entry["precedence"] = max(entry["precedence"], precedence)
            if relative not in entry["affected_paths"]:
                entry["affected_paths"].append(relative)

    cumulative = 0
    files: list[dict[str, Any]] = []
    for key in order:
        entry = selections[key]
        cumulative += entry["bytes"]
        entry["truncation_risk"] = cumulative > byte_limit
        entry["affected_paths"].sort()
        files.append(entry)

    conflicts: list[dict[str, Any]] = []
    if conflicts_file is not None:
        raw_conflicts = load_json(conflicts_file)
        if not isinstance(raw_conflicts, list):
            raise PlanAnvilError("Instruction conflicts file must contain an array", code="INVALID_INSTRUCTION_CONFLICTS")
        known_paths = {entry["path"] for entry in files}
        for item in raw_conflicts:
            if not isinstance(item, dict):
                raise PlanAnvilError("Instruction conflict must be an object", code="INVALID_INSTRUCTION_CONFLICTS")
            paths = item.get("paths")
            critical = item.get("critical")
            resolution = item.get("resolution")
            if (
                not isinstance(paths, list)
                or len(paths) < 2
                or any(not isinstance(path, str) or path not in known_paths for path in paths)
                or not isinstance(critical, bool)
                or (resolution is not None and not isinstance(resolution, str))
                or isinstance(resolution, str) and not resolution.strip()
            ):
                raise PlanAnvilError("Invalid instruction conflict entry", code="INVALID_INSTRUCTION_CONFLICTS", details=item)
            conflicts.append({"paths": sorted(set(paths)), "critical": critical, "resolution": resolution.strip() if isinstance(resolution, str) else None})

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "affected_paths": sorted(set(normalized_affected)),
        "fallback_filenames": fallback,
        "automatic_byte_limit": byte_limit,
        "files": files,
        "conflicts": conflicts,
    }

    output = output if output.is_absolute() else repo / output
    output = ensure_inside(repo, output)
    run_root = output.parent.parent if output.parent.name == "evidence" else None
    scaffolded = bool(run_root and (run_root / "state.json").is_file() and (run_root / "compliance.json").is_file())
    if scaffolded:
        state = load_json(run_root / "state.json")
        if state.get("status") != "PROFILE_READY":
            raise PlanAnvilError(
                f"Instruction mapping requires PROFILE_READY, found {state.get('status')}",
                code="INVALID_STATE_FOR_INSTRUCTION_MAP",
            )
    atomic_write_json(output, payload, exclusive=scaffolded)
    schema = Path(__file__).resolve().parent.parent / "schemas/instruction-map.schema.json"
    assert_valid_file(output, schema)

    # When the map belongs to a scaffolded run, advance canonical state and
    # record the capability without relying on conversation state.
    if scaffolded:
        compliance_path = run_root / "compliance.json"
        compliance = load_json(compliance_path)
        for capability in compliance.get("capabilities", []):
            if capability.get("id") == "CAP-INSTRUCTION-MAP":
                capability["status"] = "VERIFIED"
                capability["evidence"] = [repo_relative(repo, output)]
        compliance["verified_at"] = utc_now()
        atomic_write_json(compliance_path, compliance)
        state_path = run_root / "state.json"
        unresolved_critical = [item for item in conflicts if item["critical"] and item["resolution"] is None]
        if unresolved_critical:
            transition_state(
                state_path,
                expected_revision=state["revision"],
                new_status="BLOCKED",
                phase="REPORT_AND_STOP",
                next_action_type="NONE",
                next_action_target=None,
                blocker="BLOCKED_BY_INSTRUCTION_CONFLICT",
                hash_paths=[output],
            )
        else:
            transition_state(
                state_path,
                expected_revision=state["revision"],
                new_status="INSTRUCTION_MAP_READY",
                phase="ANALYZE_GOAL",
                next_action_type="ANALYZE_GOAL",
                next_action_target="evidence/analysis.json",
                hash_paths=[output],
            )

    blocked = any(item["critical"] and item["resolution"] is None for item in conflicts)
    return {
        "ok": not blocked,
        "result": "BLOCKED_BY_INSTRUCTION_CONFLICT" if blocked else "INSTRUCTION_MAP_READY",
        "output": repo_relative(repo, output),
        "files": len(files),
        "truncation_risk": any(item["truncation_risk"] for item in files),
        "conflicts": conflicts,
        "blocked": blocked,
        "fallback_filenames": fallback,
        "automatic_byte_limit": byte_limit,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Map complete applicable Codex project instruction files")
    parser.add_argument("--planning", type=Path, default=Path.cwd())
    parser.add_argument("--affected-path", action="append", dest="affected_paths", default=[])
    parser.add_argument("--fallback-name", action="append", dest="fallback_names")
    parser.add_argument("--automatic-byte-limit", type=int)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--conflicts-file", type=Path)
    args = parser.parse_args()
    payload = map_instructions(
        args.planning,
        affected_paths=args.affected_paths,
        output=args.output,
        fallback_filenames=args.fallback_names,
        automatic_byte_limit=args.automatic_byte_limit,
        conflicts_file=args.conflicts_file,
    )
    return emit(payload, exit_code=2 if payload.get("blocked") else 0)


if __name__ == "__main__":
    cli_main(main)
