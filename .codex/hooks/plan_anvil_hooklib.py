from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

TERMINAL_STATES = {
    "STOPPED",
    "BLOCKED",
    "FAILED",
    "USER_ACCEPTED",
    "USER_REJECTED",
    "BLOCKED_BY_UNRESOLVED_FAILURE",
}


@dataclass(frozen=True)
class ActiveRun:
    worktree: Path
    run_root: Path
    state: dict[str, Any]


def read_event() -> dict[str, Any]:
    try:
        value = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def git_root(cwd: str | None) -> Path | None:
    path = Path(cwd or ".").resolve()
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()).resolve()


def linked_worktrees(repo: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(repo), "worktree", "list", "--porcelain"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        return [repo.resolve()]
    paths: list[Path] = []
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            paths.append(Path(line.removeprefix("worktree ")).resolve())
    return paths or [repo.resolve()]


def _load_state(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def active_runs(repo: Path) -> list[ActiveRun]:
    found: list[ActiveRun] = []
    for worktree in linked_worktrees(repo):
        runs = worktree / ".pursue/runs"
        if not runs.is_dir():
            continue
        for state_path in runs.glob("*/state.json"):
            state = _load_state(state_path)
            if not state or state.get("status") in TERMINAL_STATES:
                continue
            if state.get("mode") not in {"PLAN_GENERATION", "PLAN_EXECUTION"}:
                continue
            found.append(ActiveRun(worktree.resolve(), state_path.parent.resolve(), state))
    return sorted(found, key=lambda item: item.run_root.name)


def _explicit_run_id(event: dict[str, Any]) -> str | None:
    direct = event.get("plananvil_run_id")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    environment = os.environ.get("PLANANVIL_RUN_ID")
    return environment.strip() if environment and environment.strip() else None


def active_run_for_event(event: dict[str, Any]) -> ActiveRun | None:
    raw_cwd = event.get("cwd") if isinstance(event.get("cwd"), str) else None
    repo = git_root(raw_cwd)
    if repo is None:
        return None

    candidates = [item for item in active_runs(repo) if item.worktree == repo]
    explicit = _explicit_run_id(event)
    if explicit is not None:
        matches = [item for item in candidates if item.run_root.name == explicit]
        return matches[0] if len(matches) == 1 else None

    cwd = Path(raw_cwd or repo).resolve()
    containing = [item for item in candidates if is_within(item.run_root, cwd)]
    if len(containing) == 1:
        return containing[0]
    if len(candidates) == 1:
        return candidates[0]
    return None


def event_cwd(event: dict[str, Any]) -> Path:
    raw = event.get("cwd")
    return Path(raw).resolve() if isinstance(raw, str) and raw else Path.cwd().resolve()


def is_within(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def allowed_control_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized == ".gitignore" or normalized.startswith(".pursue/")


def deny(reason: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    sys.stdout.write("\n")


def context(event_name: str, text: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": event_name,
                "additionalContext": text,
            }
        },
        sys.stdout,
    )
    sys.stdout.write("\n")


def flatten_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from flatten_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from flatten_strings(item)
