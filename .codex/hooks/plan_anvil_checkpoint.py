from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from plan_anvil_hooklib import ActiveRun

INSTALL_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = INSTALL_ROOT / ".agents/skills/plan-anvil/scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from schema_validator import validate_file  # noqa: E402


@dataclass(frozen=True)
class CheckpointValidation:
    ok: bool
    path: Path | None
    reasons: tuple[str, ...]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _safe_relative(value: str) -> bool:
    if not value or "\x00" in value:
        return False
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("//"):
        return False
    parts = PurePosixPath(normalized).parts
    return ".." not in parts and not any(part.casefold() == ".git" for part in parts)


def _resolve_checkpoint(active: ActiveRun) -> tuple[Path | None, str | None, str | None]:
    raw = active.state.get("last_checkpoint")
    if not isinstance(raw, str) or not raw.strip():
        return None, None, "state.last_checkpoint is empty"
    raw = raw.replace("\\", "/")
    if not _safe_relative(raw):
        return None, None, "state.last_checkpoint is not a safe relative path"

    if "/" not in raw and not raw.endswith(".json"):
        raw = f"checkpoints/{raw}.json"
    if raw.startswith(".pursue/"):
        candidate = active.worktree / raw
    else:
        candidate = active.run_root / raw
    candidate = candidate.resolve(strict=False)
    checkpoints = (active.run_root / "checkpoints").resolve()
    try:
        candidate.relative_to(checkpoints)
    except ValueError:
        return None, None, "checkpoint is outside the run checkpoints directory"
    try:
        relative = candidate.relative_to(active.run_root.resolve()).as_posix()
    except ValueError:
        return None, None, "checkpoint escapes the run root"
    return candidate, relative, None


def _worktree_records(repo: Path) -> list[dict[str, str]]:
    result = subprocess.run(
        ["git", "-C", str(repo), "worktree", "list", "--porcelain"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return []
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in [*result.stdout.splitlines(), ""]:
        if not line:
            if current:
                records.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value
    return records


def _git_status(path: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(path), "status", "--porcelain=v1", "--untracked-files=all"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return None
    return "DIRTY" if result.stdout else "CLEAN"


def _find_worktree(active: ActiveRun, branch: str) -> tuple[Path | None, str | None]:
    for record in _worktree_records(active.worktree):
        recorded_branch = record.get("branch", "").removeprefix("refs/heads/")
        if recorded_branch == branch:
            path = Path(record["worktree"]).resolve()
            return path, record.get("HEAD")
    return None, None


def _resolve_evidence(active: ActiveRun, relative: str) -> Path | None:
    if not _safe_relative(relative):
        return None
    candidates = [active.run_root / relative, active.worktree / relative]
    return next((path.resolve() for path in candidates if path.is_file()), None)


def validate_checkpoint_for_run(active: ActiveRun) -> CheckpointValidation:
    reasons: list[str] = []
    checkpoint_path, checkpoint_relative, resolution_error = _resolve_checkpoint(active)
    if resolution_error:
        return CheckpointValidation(False, checkpoint_path, (resolution_error,))
    assert checkpoint_path is not None and checkpoint_relative is not None
    if not checkpoint_path.is_file():
        return CheckpointValidation(False, checkpoint_path, ("checkpoint file is missing",))

    schema = INSTALL_ROOT / ".agents/skills/plan-anvil/schemas/checkpoint.schema.json"
    schema_errors = validate_file(checkpoint_path, schema)
    if schema_errors:
        reasons.append("checkpoint schema validation failed")

    try:
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return CheckpointValidation(False, checkpoint_path, tuple([*reasons, "checkpoint JSON is unreadable"]))

    expected_checkpoint_hash = active.state.get("artifact_hashes", {}).get(checkpoint_relative)
    actual_checkpoint_hash = _sha256_file(checkpoint_path)
    if expected_checkpoint_hash != actual_checkpoint_hash:
        reasons.append("state does not contain the current checkpoint hash")
    if checkpoint.get("result") != "PASS":
        reasons.append("checkpoint result is not PASS")
    if checkpoint.get("mode") != active.state.get("mode"):
        reasons.append("checkpoint mode differs from canonical state")
    if checkpoint.get("next_action") != active.state.get("next_action"):
        reasons.append("checkpoint next action differs from canonical state")

    git_data = checkpoint.get("git") if isinstance(checkpoint.get("git"), dict) else {}
    branch = git_data.get("branch")
    if not isinstance(branch, str) or not branch:
        reasons.append("checkpoint Git branch is missing")
    else:
        worktree, head = _find_worktree(active, branch)
        if worktree is None:
            reasons.append("checkpoint branch has no linked worktree")
        else:
            if head != git_data.get("head"):
                reasons.append("checkpoint HEAD differs from the linked worktree")
            current_status = _git_status(worktree)
            if current_status is None or current_status != git_data.get("status"):
                reasons.append("checkpoint Git status differs from the linked worktree")

    for relative, expected_hash in (checkpoint.get("artifact_hashes") or {}).items():
        evidence_path = _resolve_evidence(active, relative)
        if evidence_path is None:
            reasons.append(f"checkpoint artifact is missing: {relative}")
        elif _sha256_file(evidence_path) != expected_hash:
            reasons.append(f"checkpoint artifact hash is stale: {relative}")

    evidence_groups: list[Any] = [
        (checkpoint.get("tests") or {}).get("evidence", []),
        (checkpoint.get("agent_tree") or {}).get("evidence", []),
        (checkpoint.get("write_scope") or {}).get("evidence", []),
    ]
    for group in evidence_groups:
        for relative in group if isinstance(group, list) else []:
            if not isinstance(relative, str) or _resolve_evidence(active, relative) is None:
                reasons.append(f"checkpoint evidence is missing or unsafe: {relative}")

    if not isinstance(checkpoint.get("recovery"), list) or not checkpoint.get("recovery"):
        reasons.append("checkpoint recovery instructions are empty")

    return CheckpointValidation(not reasons, checkpoint_path, tuple(reasons))
