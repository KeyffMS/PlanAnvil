from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any

from common import PlanAnvilError, discover_repo, git

_GLOB_META = re.compile(r"[*?[]")
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")


def _contains_git_component(parts: tuple[str, ...] | list[str]) -> bool:
    return any(part.casefold() == ".git" for part in parts)


def gitlink_paths(repo: Path) -> set[PurePosixPath]:
    """Return tracked submodule boundaries from the current index."""
    repo = discover_repo(repo)
    result = git(repo, "ls-files", "--stage", "-z", check=False)
    if result.returncode != 0:
        raise PlanAnvilError(
            "Could not inspect Gitlink boundaries",
            code="GITLINK_INSPECTION_FAILED",
            details=result.stderr,
        )
    found: set[PurePosixPath] = set()
    for record in result.stdout.split("\0"):
        if not record or "\t" not in record:
            continue
        metadata, raw_path = record.split("\t", 1)
        mode = metadata.split(" ", 1)[0]
        if mode == "160000":
            found.add(PurePosixPath(raw_path.replace("\\", "/")))
    return found


def _crosses_gitlink(relative: PurePosixPath, gitlink: PurePosixPath) -> bool:
    return relative == gitlink or gitlink in relative.parents


def assert_safe_repo_path(
    repo: Path,
    candidate: Path,
    *,
    allow_root: bool = True,
    allow_submodule: bool = False,
) -> Path:
    """Resolve a repository path and reject escapes, Git metadata and Gitlinks."""
    repo = discover_repo(repo)
    resolved = (candidate if candidate.is_absolute() else repo / candidate).resolve(strict=False)
    try:
        relative_path = resolved.relative_to(repo)
    except ValueError as exc:
        raise PlanAnvilError(
            f"Path escapes repository root: {resolved}",
            code="PATH_ESCAPE",
        ) from exc
    if not allow_root and relative_path == Path("."):
        raise PlanAnvilError("Repository root is not an allowed target", code="PATH_ESCAPE")
    if _contains_git_component(relative_path.parts):
        raise PlanAnvilError(
            f"Direct Git metadata path is forbidden: {resolved}",
            code="GIT_PATH_FORBIDDEN",
        )

    relative = PurePosixPath(relative_path.as_posix())
    if not allow_submodule:
        for gitlink in gitlink_paths(repo):
            if _crosses_gitlink(relative, gitlink):
                raise PlanAnvilError(
                    f"Path enters submodule boundary {gitlink.as_posix()}: {resolved}",
                    code="SUBMODULE_PATH_FORBIDDEN",
                    details={"submodule": gitlink.as_posix()},
                )
    return resolved


def assert_safe_run_root(repo: Path, candidate: Path) -> Path:
    resolved = assert_safe_repo_path(repo, candidate, allow_root=False, allow_submodule=False)
    relative = resolved.relative_to(discover_repo(repo)).as_posix()
    if not relative.startswith(".pursue/runs/"):
        raise PlanAnvilError(
            f"Run root is outside .pursue/runs: {resolved}",
            code="INVALID_RUN_ROOT",
        )
    return resolved


def _static_glob_prefix(value: str) -> PurePosixPath:
    parts: list[str] = []
    for part in PurePosixPath(value).parts:
        if _GLOB_META.search(part):
            break
        parts.append(part)
    return PurePosixPath(*parts) if parts else PurePosixPath(".")


def assert_safe_relative_glob(repo: Path, value: Any) -> str:
    """Validate a repository-relative write glob against Git metadata and Gitlinks."""
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise PlanAnvilError("Write scope must be a non-empty path glob", code="UNSAFE_WRITE_PATH")
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("//") or _WINDOWS_ABSOLUTE.match(value):
        raise PlanAnvilError(f"Absolute write scope is forbidden: {value}", code="UNSAFE_WRITE_PATH")
    parts = PurePosixPath(normalized).parts
    if ".." in parts or _contains_git_component(list(parts)):
        raise PlanAnvilError(f"Unsafe write scope: {value}", code="UNSAFE_WRITE_PATH")

    prefix = _static_glob_prefix(normalized)
    for gitlink in gitlink_paths(repo):
        if (
            prefix == PurePosixPath(".")
            or prefix == gitlink
            or prefix in gitlink.parents
            or gitlink in prefix.parents
        ):
            raise PlanAnvilError(
                f"Write scope may cross submodule boundary {gitlink.as_posix()}: {value}",
                code="SUBMODULE_PATH_FORBIDDEN",
                details={"submodule": gitlink.as_posix(), "scope": value},
            )
    return normalized
