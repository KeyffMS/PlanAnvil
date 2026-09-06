"""Bounded, content-free observations for the C09/C10 Codex processes.

No transcript, command output, prompt, thread ID or diagnostic message is persisted.
Only allowlisted structural labels, counts, booleans and exit codes leave this module.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import threading
import time
from typing import Any, BinaryIO

MAX_LINE_BYTES = 1_048_576
MAX_EVENTS = 128
EVENT_TYPES = frozenset({
    "thread.started", "turn.started", "turn.completed", "turn.failed", "error",
    "item.started", "item.updated", "item.completed", "hook.started", "hook.completed",
})
ITEM_TYPES = frozenset({
    "agent_message", "reasoning", "command_execution", "file_change", "mcp_tool_call",
    "web_search", "todo_list", "error", "collab_tool_call", "context_compaction",
})
STATUSES = frozenset({"in_progress", "completed", "failed", "declined", "cancelled"})
COMMANDS = {
    **{f"python3 -B qualification-payload/c09_probe.py {p}": f"c09_{p}" for p in ("first", "second", "finish")},
    **{f"cat qualification-payload/segment-{i:02d}.txt": f"segment_{i:02d}" for i in range(1, 5)},
    "git status --porcelain=v1 --untracked-files=all": "git_status",
    "git rev-parse HEAD": "git_head",
}


def command_label(command: Any) -> str:
    if not isinstance(command, str):
        return "other"
    try:
        words = shlex.split(command)
        if len(words) == 3 and Path(words[0]).name in {"bash", "sh", "zsh"} and words[1] in {"-c", "-lc"}:
            words = shlex.split(words[2])
        # No substring matching: extra commands cannot masquerade as a fixture read.
        for text, label in COMMANDS.items():
            if words == shlex.split(text):
                return label
    except ValueError:
        pass
    return "other"


def error_category(value: Any) -> str:
    text = str(value).lower()
    if "refresh token was already used" in text:
        return "auth_refresh_reused"
    if "401" in text or "unauthorized" in text:
        return "unauthorized"
    if "429" in text or "rate limit" in text:
        return "rate_limit"
    if "hook" in text:
        return "hook_error"
    if "compact" in text:
        return "compaction_error"
    if "sandbox" in text or "permission denied" in text:
        return "sandbox_error"
    return "other"


class StructuralEvents:
    def __init__(self) -> None:
        self.events: Counter[str] = Counter()
        self.items: Counter[str] = Counter()
        self.commands: Counter[str] = Counter()
        self.errors: Counter[str] = Counter()
        self.tail: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)
        self.completed_commands = 0
        self.file_changes = 0
        self.invalid_lines = 0
        self.oversized_lines = 0
        self.stderr_lines = 0
        self.reader_failed = False
        self._start = time.monotonic()
        self._lock = threading.Lock()

    def accept(self, raw: bytes, *, stderr: bool = False) -> None:
        with self._lock:
            if stderr:
                self.stderr_lines += 1
                if raw.strip():
                    self.errors["stderr_" + error_category(raw.decode("utf-8", "replace"))] += 1
                return
            try:
                event = json.loads(raw)
            except (ValueError, UnicodeError, RecursionError):
                self.invalid_lines += 1
                return
            if not isinstance(event, dict):
                self.invalid_lines += 1
                return
            kind = event.get("type")
            kind = kind if isinstance(kind, str) and kind in EVENT_TYPES else "other"
            self.events[kind] += 1
            row: dict[str, Any] = {"event": kind, "elapsed_ms": round((time.monotonic() - self._start) * 1000)}
            item = event.get("item")
            if isinstance(item, dict):
                item_kind = item.get("type")
                item_kind = item_kind if isinstance(item_kind, str) and item_kind in ITEM_TYPES else "other"
                self.items[item_kind] += 1
                row["item"] = item_kind
                status = item.get("status")
                if isinstance(status, str) and status in STATUSES:
                    row["status"] = status
                code = item.get("exit_code")
                if type(code) is int:
                    row["exit_code"] = code
                if item_kind == "command_execution":
                    label = command_label(item.get("command"))
                    row["command"] = label
                    if label in {"c09_first", "c09_second", "c09_finish"} and kind == "item.completed":
                        # Fixed scalar receipt only; never persist output or paths.
                        raw_output = item.get("aggregated_output", "")
                        receipt = {}
                        if isinstance(raw_output, str):
                            for line in raw_output.splitlines()[-4:]:
                                try:
                                    candidate = json.loads(line)
                                except (ValueError, RecursionError):
                                    continue
                                if isinstance(candidate, dict):
                                    receipt = candidate
                        row["c09_receipt_ok"] = (receipt.get("c09_phase") == label[4:]
                            and all(receipt.get(k) is True for k in ("checkpoint_ok", "canonical_read", "git_reconciled")))
                    if kind == "item.completed":
                        self.completed_commands += 1
                        self.commands[label] += 1
                if item_kind == "file_change" and kind == "item.completed":
                    self.file_changes += 1
                if item_kind == "error":
                    label = error_category(item.get("message", item.get("text", "")))
                    self.errors[label] += 1
                    row["error_category"] = label
            if kind in {"error", "turn.failed"}:
                label = error_category(event.get("error", event.get("message", "")))
                self.errors[label] += 1
                row["error_category"] = label
            self.tail.append(row)

    def read(self, pipe: BinaryIO, *, stderr: bool = False) -> None:
        try:
            # readline(size) bounds even a malformed stream without newlines.
            while True:
                raw = pipe.readline(MAX_LINE_BYTES + 1)
                if not raw:
                    return
                if len(raw) > MAX_LINE_BYTES:
                    with self._lock:
                        self.oversized_lines += 1
                    while raw and not raw.endswith(b"\n"):
                        raw = pipe.readline(MAX_LINE_BYTES + 1)
                    continue
                self.accept(raw, stderr=stderr)
        except Exception:
            # A diagnostic failure must never disappear in a daemon reader.
            # Persist only this flag; the caller blocks qualification.
            with self._lock:
                self.reader_failed = True
        finally:
            pipe.close()

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                "event_types": dict(sorted(self.events.items())),
                "item_types": dict(sorted(self.items.items())),
                "completed_command_items": self.completed_commands,
                "completed_file_change_items": self.file_changes,
                "error_events": self.events["error"],
                "command_counts": dict(sorted(self.commands.items())),
                "error_categories": dict(sorted(self.errors.items())),
                "event_tail": list(self.tail),
                "event_tail_truncated": sum(self.events.values()) > MAX_EVENTS,
                "invalid_json_lines": self.invalid_lines,
                "oversized_lines": self.oversized_lines,
                "stderr_lines": self.stderr_lines,
                "reader_failed": self.reader_failed,
            }


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    timed_out: bool
    events: dict[str, Any]


def _kill_owned_tree(process: subprocess.Popen[bytes]) -> bool:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
            return True
        except ProcessLookupError:
            return True
        except OSError:
            process.kill()
            return False
    try:
        killed = subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False,
        )
        if killed.returncode == 0:
            return True
    except (OSError, subprocess.TimeoutExpired):
        pass
    if process.poll() is None:
        process.kill()
    return False


def run_observed(args: list[str], *, cwd: Path, timeout: float) -> ProcessResult:
    """Kill the owned process group/tree on timeout and retain partial event structure."""
    if timeout <= 0:
        raise ValueError("Process timeout must be positive")
    options: dict[str, Any] = {"start_new_session": True} if os.name == "posix" else {
        "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP,
    }
    started = time.monotonic()
    process = subprocess.Popen(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options)
    assert process.stdout is not None and process.stderr is not None
    collector = StructuralEvents()
    readers = [
        threading.Thread(target=collector.read, args=(process.stdout,), daemon=True),
        threading.Thread(target=collector.read, args=(process.stderr,), kwargs={"stderr": True}, daemon=True),
    ]
    for reader in readers:
        reader.start()
    timed_out = False
    cleanup_ok = True
    tree_terminated = False
    try:
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            tree_terminated = True
            cleanup_ok = _kill_owned_tree(process)
            process.wait(timeout=10)
        for reader in readers:
            reader.join(timeout=1)
        if any(reader.is_alive() for reader in readers):
            # A launcher may exit while a child still owns stdout/stderr.
            tree_terminated = True
            cleanup_ok = _kill_owned_tree(process) and cleanup_ok
            for reader in readers:
                reader.join(timeout=5)
    except BaseException:
        _kill_owned_tree(process)
        process.wait(timeout=10)
        for reader in readers:
            reader.join(timeout=5)
        raise
    events = collector.summary()
    events.update({
        "timeout": timed_out,
        "process_returncode": process.returncode,
        "process_elapsed_ms": round((time.monotonic() - started) * 1000),
        "owned_process_tree_terminated": tree_terminated,
        "process_cleanup_ok": cleanup_ok and not any(reader.is_alive() for reader in readers),
    })
    return ProcessResult(process.returncode, timed_out, events)
