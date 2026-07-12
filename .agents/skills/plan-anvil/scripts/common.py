from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlsplit, urlunsplit

SCHEMA_VERSION = "1.1.0"
GENERATOR_VERSION = "0.1.0"
CONTRACT_VERSION = "2.1"

PLAN_ID_RE = re.compile(r"^PG-\d{8}-\d{6}-[A-F0-9]{4}$")
RUN_ID_RE = re.compile(
    r"^\d{8}T\d{6}Z_PG-\d{8}-\d{6}-[A-F0-9]{4}_[a-z0-9]+(?:-[a-z0-9]+)*$"
)
STAGE_ID_RE = re.compile(r"^STAGE-\d{2}[A-Z]?$")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SHA_RE = re.compile(r"^[0-9a-f]{40,64}$")

GENERATOR_STATES = [
    "NEW",
    "SOURCE_PREFLIGHT_PASSED",
    "GIT_READY",
    "PLANNING_WORKTREE_READY",
    "PROFILE_READY",
    "INSTRUCTION_MAP_READY",
    "ANALYSIS_READY",
    "ARTIFACTS_GENERATED",
    "DETERMINISTICALLY_VALID",
    "BLIND_REVIEW_WRITTEN",
    "COMPARISON_VALID",
    "PLAN_COMMITTED",
    "STOPPED",
]

TERMINAL_PLAN_STATUSES = {
    "PLAN_READY",
    "BLOCKED_BY_CRITICAL_UNKNOWN",
    "BLOCKED_BY_GIT_STATE",
    "BLOCKED_BY_GIT_PERMISSIONS",
    "BLOCKED_BY_INSTRUCTION_CONFLICT",
    "BLOCKED_BY_RUNTIME_PREREQUISITE",
    "PLAN_VALIDATION_FAILED",
}

SECRET_PATTERNS = [
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("generic-token", re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|secret|password)\b\s*[:=]\s*[\"']?[A-Za-z0-9_./+=-]{12,}")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
]

ABSOLUTE_PATH_PATTERNS = [
    re.compile(r"(?<![A-Za-z0-9_.-])/(?:home|Users|private|var|tmp|opt|srv|mnt|Volumes)/[^\s`\"'<>]+"),
    re.compile(r"(?i)(?<![A-Za-z0-9])(?:[A-Z]:[\\/])[^\s`\"'<>]+"),
    re.compile(r"\\\\[^\\\s]+\\[^\\\s]+"),
    re.compile(r"(?<![A-Za-z0-9_.-])~[/\\][^\s`\"'<>]+"),
]


class PlanAnvilError(RuntimeError):
    def __init__(self, message: str, *, code: str = "PLANANVIL_ERROR", details: Any = None):
        super().__init__(message)
        self.code = code
        self.details = details


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def timestamp_id() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def make_plan_id() -> str:
    now = dt.datetime.now(dt.timezone.utc)
    return f"PG-{now:%Y%m%d-%H%M%S}-{secrets.token_hex(2).upper()}"


def slugify(value: str, *, default: str = "plan", max_length: int = 48) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    value = re.sub(r"-{2,}", "-", value)
    return (value[:max_length].rstrip("-") or default)


def make_run_id(plan_id: str, slug: str) -> str:
    if not PLAN_ID_RE.fullmatch(plan_id):
        raise PlanAnvilError(f"Invalid plan id: {plan_id}", code="INVALID_PLAN_ID")
    return f"{timestamp_id()}_{plan_id}_{slugify(slug)}"


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def canonical_json_text(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def atomic_write_text(path: Path, text: str, *, exclusive: bool = False) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive and path.exists():
        raise PlanAnvilError(f"Refusing to overwrite immutable file: {path}", code="IMMUTABLE_EXISTS")
    mode = "x" if exclusive else "w"
    if exclusive:
        with path.open(mode, encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        return
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
        except (AttributeError, OSError):
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if tmp.exists():
            tmp.unlink()


def atomic_write_json(path: Path, value: Any, *, exclusive: bool = False) -> None:
    atomic_write_text(path, canonical_json_text(value), exclusive=exclusive)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PlanAnvilError(f"Missing JSON file: {path}", code="MISSING_FILE") from exc
    except json.JSONDecodeError as exc:
        raise PlanAnvilError(
            f"Invalid JSON in {path}: line {exc.lineno}, column {exc.colno}",
            code="INVALID_JSON",
        ) from exc


def command(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    timeout: int = 120,
) -> CommandResult:
    process = subprocess.run(
        list(args),
        cwd=str(cwd) if cwd else None,
        env=env,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        shell=False,
    )
    result = CommandResult(tuple(str(x) for x in args), process.returncode, process.stdout, process.stderr)
    if check and process.returncode != 0:
        raise PlanAnvilError(
            f"Command failed ({process.returncode}): {' '.join(result.args)}",
            code="COMMAND_FAILED",
            details={"stdout": result.stdout, "stderr": result.stderr},
        )
    return result


def git(
    repo: Path,
    *args: str,
    check: bool = True,
    timeout: int = 120,
    env: dict[str, str] | None = None,
) -> CommandResult:
    return command(["git", "-C", str(repo), *args], check=check, timeout=timeout, env=env)


def discover_repo(path: Path) -> Path:
    result = git(path, "rev-parse", "--show-toplevel", check=False)
    if result.returncode != 0:
        raise PlanAnvilError("Not inside a Git repository", code="NOT_A_GIT_REPOSITORY")
    return Path(result.stdout.strip()).resolve()


def git_path(repo: Path, name: str) -> Path:
    result = git(repo, "rev-parse", "--git-path", name)
    raw = Path(result.stdout.strip())
    return raw.resolve() if raw.is_absolute() else (repo / raw).resolve()


def detect_git_operation(repo: Path) -> str | None:
    checks = [
        ("MERGE", "MERGE_HEAD"),
        ("CHERRY_PICK", "CHERRY_PICK_HEAD"),
        ("REVERT", "REVERT_HEAD"),
        ("BISECT", "BISECT_LOG"),
        ("REBASE", "rebase-merge"),
        ("REBASE", "rebase-apply"),
    ]
    for label, name in checks:
        if git_path(repo, name).exists():
            return label
    return None


def source_snapshot(repo: Path) -> dict[str, Any]:
    repo = discover_repo(repo)
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    branch_result = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else None
    status = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout.encode("utf-8", "surrogateescape")
    index = git(repo, "ls-files", "--stage", "-z").stdout.encode("utf-8", "surrogateescape")
    return {
        "head": head,
        "branch": branch,
        "status_hash": sha256_bytes(status),
        "index_hash": sha256_bytes(index),
    }


def compare_snapshot(repo: Path, expected: dict[str, Any]) -> list[str]:
    current = source_snapshot(repo)
    return [key for key in ("head", "branch", "status_hash", "index_hash") if current.get(key) != expected.get(key)]




def path_is_within(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def git_worktree_paths(repo: Path) -> list[Path]:
    repo = discover_repo(repo)
    result = git(repo, "worktree", "list", "--porcelain", check=False)
    if result.returncode != 0:
        raise PlanAnvilError("Could not list Git worktrees", code="GIT_WORKTREE_UNSUPPORTED", details=result.stderr)
    paths = [
        Path(line.removeprefix("worktree ")).resolve()
        for line in result.stdout.splitlines()
        if line.startswith("worktree ")
    ]
    return paths or [repo]


def require_external_path(repo: Path, candidate: Path, *, code: str) -> Path:
    resolved = candidate.resolve()
    for worktree in git_worktree_paths(repo):
        if path_is_within(worktree, resolved):
            raise PlanAnvilError(
                f"Path must be outside every repository worktree: {resolved}",
                code=code,
                details={"worktree": str(worktree), "candidate": str(resolved)},
            )
    return resolved

def repository_fingerprint(repo: Path) -> str:
    repo = discover_repo(repo)
    remote = git(repo, "config", "--get", "remote.origin.url", check=False).stdout.strip()
    if remote:
        identity = sanitize_remote_identity(remote)
    else:
        roots = git(repo, "rev-list", "--max-parents=0", "--all", check=False).stdout.splitlines()
        identity = "roots:" + ",".join(sorted(roots))
    return sha256_text(identity)


def sanitize_remote_identity(remote: str) -> str:
    remote = remote.strip()
    scp_match = re.match(r"^(?:[^@]+@)?([^:]+):(.+)$", remote)
    if scp_match and "://" not in remote:
        host, path = scp_match.groups()
        return f"{host.lower()}/{path.removesuffix('.git')}"
    parts = urlsplit(remote)
    if parts.scheme and parts.netloc:
        host = parts.hostname or parts.netloc
        port = f":{parts.port}" if parts.port else ""
        path = parts.path.removesuffix(".git")
        return urlunsplit((parts.scheme.lower(), host.lower() + port, path, "", ""))
    return remote.removesuffix(".git")


def ensure_inside(root: Path, candidate: Path, *, allow_root: bool = True) -> Path:
    root = root.resolve()
    candidate = candidate.resolve(strict=False)
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise PlanAnvilError(f"Path escapes allowed root: {candidate}", code="PATH_ESCAPE") from exc
    if not allow_root and relative == Path("."):
        raise PlanAnvilError("Root path is not an allowed target", code="PATH_ESCAPE")
    if ".git" in relative.parts:
        raise PlanAnvilError(f"Direct .git write is forbidden: {candidate}", code="GIT_PATH_FORBIDDEN")
    return candidate


def repo_relative(root: Path, path: Path) -> str:
    return ensure_inside(root, path).relative_to(root.resolve()).as_posix() or "."


def append_ignore_rules(repo: Path, rules: Iterable[str]) -> bool:
    repo = discover_repo(repo)
    ignore = repo / ".gitignore"
    existing = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
    lines = existing.splitlines()
    missing = [rule for rule in rules if rule not in lines]
    if not missing:
        return False
    block = "\n".join(["", "# PlanAnvil local state", *missing, ""])
    atomic_write_text(ignore, existing.rstrip("\n") + block)
    return True


def is_ignored(repo: Path, path: Path) -> bool:
    relative = repo_relative(repo, path)
    return git(repo, "check-ignore", "-q", "--", relative, check=False).returncode == 0


def is_tracked(repo: Path, path: Path) -> bool:
    relative = repo_relative(repo, path)
    return git(repo, "ls-files", "--error-unmatch", "--", relative, check=False).returncode == 0


def list_untracked(repo: Path) -> list[str]:
    result = git(repo, "ls-files", "--others", "--exclude-standard", "-z")
    return [item for item in result.stdout.split("\0") if item]


def privacy_findings(path: Path, text: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for name, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            findings.append({"path": path.as_posix(), "kind": name})
    for pattern in ABSOLUTE_PATH_PATTERNS:
        match = pattern.search(text)
        if match:
            findings.append({"path": path.as_posix(), "kind": "absolute-path", "sample": match.group(0)[:120]})
    return findings


def scan_privacy(root: Path, paths: Iterable[Path]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = Path(repo_relative(root, path))
        findings.extend(privacy_findings(rel, text))
    return findings


def emit(payload: dict[str, Any], *, exit_code: int = 0) -> int:
    sys.stdout.write(canonical_json_text(payload))
    return exit_code


def fail_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, PlanAnvilError):
        return {"ok": False, "error": exc.code, "message": str(exc), "details": exc.details}
    return {"ok": False, "error": exc.__class__.__name__, "message": str(exc)}


def cli_main(function) -> None:
    try:
        code = function()
    except Exception as exc:  # top-level machine-readable failure boundary
        emit(fail_payload(exc), exit_code=1)
        raise SystemExit(1)
    raise SystemExit(code if isinstance(code, int) else 0)


def add_source_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", type=Path, default=Path.cwd(), help="Source repository or path inside it")


def canonical_file_is_valid(path: Path) -> bool:
    try:
        value = load_json(path)
    except PlanAnvilError:
        return False
    return path.read_text(encoding="utf-8") == canonical_json_text(value)
