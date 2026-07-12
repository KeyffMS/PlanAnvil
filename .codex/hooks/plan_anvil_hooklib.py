from __future__ import annotations

import json
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
        return [repo]
    paths: list[Path] = []
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            paths.append(Path(line.removeprefix("worktree ")).resolve())
    return paths or [repo]


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
            found.append(ActiveRun(worktree, state_path.parent, state))
    return sorted(found, key=lambda item: item.run_root.name)


def active_run_for_event(event: dict[str, Any]) -> ActiveRun | None:
    repo = git_root(event.get("cwd") if isinstance(event.get("cwd"), str) else None)
    if repo is None:
        return None
    runs = active_runs(repo)
    return runs[-1] if runs else None


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
