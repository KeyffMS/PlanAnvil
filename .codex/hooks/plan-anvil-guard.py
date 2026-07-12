from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from plan_anvil_hooklib import (
    active_run_for_event,
    allowed_control_path,
    deny,
    event_cwd,
    flatten_strings,
    is_within,
    read_event,
)

DANGEROUS_GIT = re.compile(
    r"(?is)(?:^|[;&|]\s*)git(?:\s+-C\s+\S+)?\s+(?:stash|reset|clean|push|merge|rebase|cherry-pick|revert|checkout|switch)\b"
)
DANGEROUS_RUNTIME = re.compile(
    r"(?is)(?:^|[;&|]\s*)(?:rm\s+-rf|del\s+/[sq]|remove-item\b[^\n]*-recurse|"
    r"kubectl\s+(?:apply|delete|rollout|scale)|terraform\s+(?:apply|destroy)|"
    r"systemctl\s+(?:start|stop|restart)|docker(?:\s+compose)?\s+(?:up|down|restart)|"
    r"npm\s+publish|composer\s+publish)\b"
)
PATCH_PATH = re.compile(r"(?m)^\*\*\*\s+(?:Add|Update|Delete)\s+File:\s*(.+?)\s*$")
UNIFIED_PATH = re.compile(r"(?m)^\+\+\+\s+(?:b/)?([^\t\n]+)")
WRITE_WORDS = re.compile(r"(?i)\b(?:write|create|update|edit|patch|delete|remove|move|rename|replace)\b")
PATH_KEYS = {"path", "file_path", "file", "filename", "target", "destination", "output", "root"}


def _command(tool_input: Any) -> str:
    if isinstance(tool_input, dict):
        value = tool_input.get("command")
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return " ".join(str(item) for item in value)
    return ""


def _patch_paths(command: str) -> list[str]:
    paths = PATCH_PATH.findall(command)
    paths.extend(path for path in UNIFIED_PATH.findall(command) if path != "/dev/null")
    return [path.strip().strip('"\'') for path in paths]


def _mcp_paths(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in PATH_KEYS and isinstance(item, str):
                found.append(item)
            else:
                found.extend(_mcp_paths(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_mcp_paths(item))
    return found


def main() -> int:
    event = read_event()
    active = active_run_for_event(event)
    if active is None or active.state.get("mode") != "PLAN_GENERATION":
        return 0

    tool = str(event.get("tool_name") or "")
    tool_input = event.get("tool_input")
    cwd = event_cwd(event)

    if tool == "Bash":
        command = _command(tool_input)
        if DANGEROUS_GIT.search(command):
            deny("PlanAnvil generation forbids destructive or integrating Git commands. Use only the deterministic PlanAnvil scripts and planning-control branch.")
            return 0
        if DANGEROUS_RUNTIME.search(command):
            deny("PlanAnvil generates a plan only; deployment, migration, service switching, publication, and destructive cleanup are forbidden.")
            return 0
        return 0

    if tool in {"Edit", "Write"}:
        if not is_within(active.worktree, cwd):
            deny("PlanAnvil file edits are permitted only in the isolated planning worktree.")
            return 0
        paths = _mcp_paths(tool_input)
        if not paths:
            deny("PlanAnvil could not prove the file-edit target is an allowed planning-control path.")
            return 0
        for raw_path in paths:
            candidate = Path(raw_path)
            if candidate.is_absolute():
                try:
                    relative = candidate.resolve().relative_to(active.worktree.resolve()).as_posix()
                except (OSError, ValueError):
                    deny("PlanAnvil file edits may not escape the planning worktree.")
                    return 0
            else:
                relative = candidate.as_posix()
            if ".." in Path(relative).parts or not allowed_control_path(relative):
                deny("PlanAnvil file edits may modify only .pursue/** and .gitignore inside the planning worktree.")
                return 0
        return 0

    if tool == "apply_patch":
        if not is_within(active.worktree, cwd):
            deny("PlanAnvil file edits are permitted only in the isolated planning worktree.")
            return 0
        command = _command(tool_input)
        paths = _patch_paths(command)
        if not paths:
            deny("PlanAnvil could not prove the apply_patch target is an allowed planning-control path.")
            return 0
        escaped = [path for path in paths if Path(path).is_absolute() or ".." in Path(path).parts]
        forbidden = [path for path in paths if not allowed_control_path(path)]
        if escaped or forbidden:
            deny("PlanAnvil apply_patch may modify only .pursue/** and .gitignore inside the planning worktree.")
        return 0

    if tool.startswith("mcp__"):
        text = " ".join(flatten_strings(tool_input))
        if not WRITE_WORDS.search(tool + " " + text):
            return 0
        if not is_within(active.worktree, cwd):
            deny("PlanAnvil write-capable MCP calls are permitted only in the isolated planning worktree.")
            return 0
        paths = _mcp_paths(tool_input)
        if not paths or any(Path(path).is_absolute() or ".." in Path(path).parts or not allowed_control_path(path) for path in paths):
            deny("PlanAnvil write-capable MCP calls must prove every target is under .pursue/** or is .gitignore.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
