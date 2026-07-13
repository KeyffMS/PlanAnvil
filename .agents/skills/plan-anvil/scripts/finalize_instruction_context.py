from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from common import PlanAnvilError, atomic_write_json, atomic_write_text, load_json
from schema_validator import assert_valid_file
from validate_plan import _frontmatter

_SECTION_RE = re.compile(
    r"(?ms)^## Project instruction map\n.*?(?=^## |\Z)"
)


def finalize_instruction_context(repo: Path, run: Path) -> dict[str, Any]:
    instruction_path = run / "evidence/instruction-map.json"
    profile_path = repo / ".pursue/SYSTEM_PROFILE.md"
    instruction_map = load_json(instruction_path)
    files = instruction_map.get("files")
    if not isinstance(files, list):
        raise PlanAnvilError("Instruction map files must be an array", code="INVALID_INSTRUCTION_MAP")

    stages_by_instruction: dict[tuple[str, str], set[str]] = {}
    for stage_path in sorted((run / "stages").glob("STAGE-*.md")):
        metadata = _frontmatter(stage_path)
        stage_id = metadata.get("stage_id")
        if not isinstance(stage_id, str):
            continue
        references = metadata.get("applicable_instructions")
        if not isinstance(references, list):
            continue
        for reference in references:
            if not isinstance(reference, dict):
                continue
            path = reference.get("path")
            digest = reference.get("sha256")
            if isinstance(path, str) and isinstance(digest, str):
                stages_by_instruction.setdefault((path, digest), set()).add(stage_id)

    normalized_files: list[dict[str, Any]] = []
    for entry in files:
        if not isinstance(entry, dict):
            raise PlanAnvilError("Instruction map entry must be an object", code="INVALID_INSTRUCTION_MAP")
        path = entry.get("path")
        digest = entry.get("sha256")
        affected_stages = sorted(stages_by_instruction.get((path, digest), set()))
        if not affected_stages:
            raise PlanAnvilError(
                f"Instruction is not assigned to any stage: {path}",
                code="INSTRUCTION_WITHOUT_AFFECTED_STAGE",
            )
        normalized_files.append({**entry, "affected_stages": affected_stages})

    updated_map = {**instruction_map, "files": normalized_files}
    atomic_write_json(instruction_path, updated_map)
    schema = Path(__file__).resolve().parent.parent / "schemas/instruction-map.schema.json"
    assert_valid_file(instruction_path, schema)

    profile = profile_path.read_text(encoding="utf-8")
    lines = ["## Project instruction map", ""]
    for entry in normalized_files:
        stages = ", ".join(entry["affected_stages"])
        lines.append(
            f"- `{entry['path']}` (`{entry['sha256']}`) — scope `{entry['scope']}`, "
            f"precedence `{entry['precedence']}`, stages: {stages}."
        )
    replacement = "\n".join(lines).rstrip() + "\n\n"
    if not _SECTION_RE.search(profile):
        raise PlanAnvilError("Repository profile instruction section is missing", code="PROFILE_INSTRUCTION_SECTION_MISSING")
    updated_profile = _SECTION_RE.sub(replacement, profile, count=1)
    atomic_write_text(profile_path, updated_profile)

    return {
        "ok": True,
        "result": "INSTRUCTION_CONTEXT_FINALIZED",
        "files": len(normalized_files),
        "stages": sorted({stage for entry in normalized_files for stage in entry["affected_stages"]}),
    }
