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
    atomic_write_text,
    cli_main,
    discover_repo,
    emit,
    ensure_inside,
    load_json,
    repo_relative,
    sha256_bytes,
    utc_now,
)
from path_safety import assert_safe_repo_path
from schema_validator import assert_valid_file
from transition_state import run_lock, transition_state


SAFETY_TERMS = re.compile(
    r"(?i)\b(?:must not|never|forbidden|secret|credential|production|deploy|destructive|irreversible|security|privacy|legal|permission|protected branch|data loss)\b"
)


def _codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser().resolve()


def _load_codex_instruction_config(repo: Path) -> tuple[list[str], int]:
    fallback: list[str] = []
    max_bytes = 32768
    for path in [_codex_home() / "config.toml", repo / ".codex/config.toml"]:
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
    candidate = assert_safe_repo_path(repo, raw if raw.is_absolute() else repo / raw)
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


def _global_instruction() -> Path | None:
    home = _codex_home()
    for name in ["AGENTS.override.md", "AGENTS.md"]:
        path = home / name
        if path.is_file() and path.stat().st_size > 0:
            return path
    return None


def _entry(path: Path, *, display_path: str, scope: str, precedence: int) -> dict[str, Any]:
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PlanAnvilError(f"Instruction file is not UTF-8: {display_path}", code="INSTRUCTION_NOT_UTF8") from exc
    safety_rules = [
        f"L{number} {sha256_bytes(line.encode('utf-8'))}"
        for number, line in enumerate(text.splitlines(), start=1)
        if SAFETY_TERMS.search(line)
    ]
    return {
        "path": display_path,
        "sha256": sha256_bytes(data),
        "bytes": len(data),
        "full_read": True,
        "scope": scope,
        "precedence": precedence,
        "affected_paths": [],
        "truncation_risk": False,
        "safety_critical_rules": safety_rules,
    }


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
    affected_paths = affected_paths or ["."]
    configured_fallback, configured_limit = _load_codex_instruction_config(repo)
    fallback = list(dict.fromkeys(fallback_filenames if fallback_filenames is not None else configured_fallback))
    byte_limit = automatic_byte_limit or configured_limit

    normalized_affected: list[str] = []
    selections: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    global_path = _global_instruction()
    if global_path is not None:
        key = global_path.resolve().as_posix()
        selections[key] = _entry(
            global_path,
            display_path=f"$CODEX_HOME/{global_path.name}",
            scope="GLOBAL",
            precedence=-1,
        )
        order.append(key)

    for affected in affected_paths:
        absolute = assert_safe_repo_path(repo, Path(affected))
        relative = repo_relative(repo, absolute)
        normalized_affected.append(relative)
        if global_path is not None:
            selections[global_path.resolve().as_posix()]["affected_paths"].append(relative)
        for precedence, directory in enumerate(_scope_directories(repo, relative)):
            selected = _selected_instruction(directory, fallback)
            if selected is None:
                continue
            key = selected.resolve().as_posix()
            if key not in selections:
                selections[key] = _entry(
                    selected,
                    display_path=repo_relative(repo, selected),
                    scope=repo_relative(repo, directory),
                    precedence=precedence,
                )
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
        entry["affected_paths"] = sorted(set(entry["affected_paths"]))
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
            conflicts.append({
                "paths": sorted(set(paths)),
                "critical": critical,
                "resolution": resolution.strip() if isinstance(resolution, str) else None,
            })

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "affected_paths": sorted(set(normalized_affected)),
        "fallback_filenames": fallback,
        "automatic_byte_limit": byte_limit,
        "files": files,
        "conflicts": conflicts,
    }

    output = ensure_inside(repo, output if output.is_absolute() else repo / output)
    run_root = output.parent.parent if output.parent.name == "evidence" else None
    scaffolded = bool(run_root and (run_root / "state.json").is_file() and (run_root / "compliance.json").is_file())
    instruction_schema = Path(__file__).resolve().parent.parent / "schemas/instruction-map.schema.json"

    if scaffolded:
        state_path = run_root / "state.json"
        compliance_path = run_root / "compliance.json"
        with run_lock(state_path, command="map-instructions"):
            state = load_json(state_path)
            if state.get("status") != "PROFILE_READY":
                raise PlanAnvilError(
                    f"Instruction mapping requires PROFILE_READY, found {state.get('status')}",
                    code="INVALID_STATE_FOR_INSTRUCTION_MAP",
                )
            original_compliance = compliance_path.read_text(encoding="utf-8")
            created_output = False
            try:
                atomic_write_json(output, payload, exclusive=True)
                created_output = True
                assert_valid_file(output, instruction_schema)

                compliance = load_json(compliance_path)
                for capability in compliance.get("capabilities", []):
                    if capability.get("id") == "CAP-INSTRUCTION-MAP":
                        capability["status"] = "VERIFIED"
                        capability["evidence"] = [repo_relative(repo, output)]
                compliance["verified_at"] = utc_now()
                atomic_write_json(compliance_path, compliance)
                compliance_schema = Path(__file__).resolve().parent.parent / "schemas/compliance.schema.json"
                assert_valid_file(compliance_path, compliance_schema)

                unresolved = [item for item in conflicts if item["critical"] and item["resolution"] is None]
                transition_state(
                    state_path,
                    expected_revision=state["revision"],
                    new_status="BLOCKED" if unresolved else "INSTRUCTION_MAP_READY",
                    phase="REPORT_AND_STOP" if unresolved else "ANALYZE_GOAL",
                    next_action_type="NONE" if unresolved else "ANALYZE_GOAL",
                    next_action_target=None if unresolved else "evidence/analysis.json",
                    blocker="BLOCKED_BY_INSTRUCTION_CONFLICT" if unresolved else None,
                    hash_paths=[output],
                    lock_held=True,
                )
            except Exception:
                atomic_write_text(compliance_path, original_compliance)
                if created_output:
                    output.unlink(missing_ok=True)
                raise
    else:
        atomic_write_json(output, payload)
        assert_valid_file(output, instruction_schema)

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
