from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from common import (
    PlanAnvilError,
    append_ignore_rules,
    atomic_write_text,
    cli_main,
    discover_repo,
    emit,
    git,
    repository_fingerprint,
    sha256_file,
    utc_now,
)

EXTENSION_NAMES = {
    ".py": "Python",
    ".php": "PHP",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript/TSX",
    ".jsx": "JavaScript/JSX",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".cs": "C#",
    ".cpp": "C++",
    ".c": "C",
    ".h": "C/C++ header",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".sql": "SQL",
    ".sh": "Shell",
    ".ps1": "PowerShell",
    ".svg": "SVG",
}

MANIFEST_HINTS = {
    "pyproject.toml": ("Python", "python -m unittest discover"),
    "requirements.txt": ("Python", "python -m unittest discover"),
    "package.json": ("Node.js", None),
    "composer.json": ("PHP", "composer test"),
    "go.mod": ("Go", "go test ./..."),
    "Cargo.toml": ("Rust", "cargo test"),
    "pom.xml": ("Java/Maven", "mvn test"),
    "build.gradle": ("Java/Gradle", "./gradlew test"),
    "build.gradle.kts": ("Kotlin/Gradle", "./gradlew test"),
    "Gemfile": ("Ruby", "bundle exec rake test"),
}

FRESHNESS_NAMES = {
    "AGENTS.md", "AGENTS.override.md", "package.json", "package-lock.json", "pnpm-lock.yaml",
    "yarn.lock", "composer.json", "composer.lock", "pyproject.toml", "requirements.txt",
    "poetry.lock", "uv.lock", "go.mod", "go.sum", "Cargo.toml", "Cargo.lock", "pom.xml",
    "build.gradle", "build.gradle.kts", "Gemfile", "Gemfile.lock", "Dockerfile",
    "docker-compose.yml", "docker-compose.yaml", "Makefile", "Taskfile.yml", "Taskfile.yaml",
    "phpunit.xml", "phpunit.xml.dist", "pytest.ini", "tox.ini", "mypy.ini", "ruff.toml",
}
FRESHNESS_PARTS = {
    ".github", ".gitlab", ".codex", "migrations", "migration", "deploy", "deployment",
    "helm", "k8s", "kubernetes", "terraform", "ansible", "ci", "scripts",
}


def _freshness_files(repo: Path, files: list[Path]) -> list[Path]:
    selected: list[Path] = []
    for path in files:
        rel = path.relative_to(repo)
        lower_parts = {part.lower() for part in rel.parts}
        if (
            path.name in FRESHNESS_NAMES
            or path.name.startswith("AGENTS.")
            or bool(lower_parts & FRESHNESS_PARTS)
            or any(token in path.name.lower() for token in ("test", "build", "deploy", "migration", "schema"))
        ):
            selected.append(path)
    return sorted(set(selected), key=lambda item: item.relative_to(repo).as_posix())[:250]


def _tracked_files(repo: Path) -> list[Path]:
    raw = git(repo, "ls-files", "-z").stdout
    return [repo / item for item in raw.split("\0") if item]


def _json_scripts(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    scripts = data.get("scripts")
    if not isinstance(scripts, dict):
        return []
    return [f"{name}: {value}" for name, value in sorted(scripts.items()) if isinstance(value, str)]


def profile_repository(planning: Path, source: Path) -> dict[str, Any]:
    repo = discover_repo(planning)
    source_repo = discover_repo(source)
    branch = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False).stdout.strip()
    if not branch.startswith("pursue/plan/"):
        raise PlanAnvilError("Repository is not on a PlanAnvil planning branch", code="NOT_PLANNING_WORKTREE")

    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    files = _tracked_files(repo)
    extension_counts = Counter(path.suffix.lower() for path in files if path.suffix)
    languages = [
        (EXTENSION_NAMES[ext], count)
        for ext, count in extension_counts.most_common()
        if ext in EXTENSION_NAMES
    ]
    manifests: list[str] = []
    command_lines: list[str] = []
    runtimes: list[str] = []
    for filename, (runtime, default_command) in MANIFEST_HINTS.items():
        path = repo / filename
        if path.exists():
            manifests.append(filename)
            runtimes.append(runtime)
            if default_command:
                command_lines.append(f"- `{default_command}` — inferred from `{filename}`; verify before execution")
            if filename in {"package.json", "composer.json"}:
                for script in _json_scripts(path):
                    command_lines.append(f"- `{script}` — declared in `{filename}`")

    top_level = sorted({path.relative_to(repo).parts[0] for path in files if path.relative_to(repo).parts})
    ci = sorted(
        path.relative_to(repo).as_posix()
        for path in files
        if path.relative_to(repo).as_posix().startswith((".github/workflows/", ".gitlab-ci", "azure-pipelines"))
    )
    freshness_files = _freshness_files(repo, files)
    freshness_lines = [
        f"- `{path.relative_to(repo).as_posix()}`: `{sha256_file(path)}`"
        for path in freshness_files
        if path.is_file()
    ]

    structure = "\n".join(f"- `{item}`" for item in top_level[:80]) or "- No tracked files detected."
    language_text = "\n".join(f"- {name}: {count} tracked files" for name, count in languages[:20]) or "- UNKNOWN"
    runtime_text = "\n".join(f"- {name}" for name in sorted(set(runtimes))) or "- UNKNOWN"
    commands = "\n".join(command_lines) or "- UNKNOWN — derive from repository instructions and manifests before planning acceptance."
    ci_text = "\n".join(f"- `{item}`" for item in ci) or "- No tracked CI definition detected."
    generated = utc_now()
    fingerprint = repository_fingerprint(repo)

    profile = f"""# PlanAnvil Repository Profile

- Profile status: `VALID_WITH_UNKNOWNS`
- Generated at: `{generated}`
- Repository fingerprint: `{fingerprint}`
- Evidence base SHA: `{head}`

## Repository structure and architecture

Tracked top-level entries:

{structure}

Architecture is not inferred beyond repository evidence. The plan must identify concrete components and flows for the requested goal.

## Languages, runtimes, and dependency managers

Languages:

{language_text}

Runtime/dependency indicators:

{runtime_text}

Tracked manifests: {", ".join(f"`{item}`" for item in manifests) if manifests else "none detected"}.

## Build, test, lint, and static-analysis commands

{commands}

Commands marked inferred require confirmation from project instructions or a non-mutating discovery step before use.

## Git conventions and quality gates

- Current planning branch: `{branch}`
- Evidence SHA: `{head}`
- Source worktree must remain unchanged.
- Product changes are forbidden in this planning worktree.
- Commit signing and repository hooks must remain enabled according to repository policy.
- CI definitions:

{ci_text}

## Project instruction map

Pending explicit instruction mapping. The run-specific instruction map is authoritative.

## Deployment, state, and rollback rules

- Deployment behavior: `UNKNOWN`
- Push-trigger implications: stored only in the ignored local profile when discovered.
- Stateful changes require recovery points, compatibility, resumability, integrity checks, observation, and separate contraction.
- Live switching and irreversible operations require explicit user approval.

## Risk and activation policy

- LOW: isolated behavior with focused evidence.
- MEDIUM: cross-component or public behavior with bounded rollback.
- HIGH: stateful, destructive, security-sensitive, permission-sensitive, or live-system work.
- Critical unknowns block readiness.

## Evidence and freshness

- Profile facts are `VERIFIED`, `INFERRED`, or `UNKNOWN`.
- Freshness anchor: tracked repository state at `{head}`.
- Revalidate when any hashed instruction, dependency, build/test, deployment, migration, or PlanAnvil configuration file changes.
- Hashed evidence files:

{chr(10).join(freshness_lines) if freshness_lines else "- No freshness-sensitive tracked file detected."}
"""
    local_profile = f"""# PlanAnvil Local Profile

This ignored file contains non-secret machine-specific locators. Never commit it.

- Source worktree: `{source_repo.resolve()}`
- Planning worktree: `{repo.resolve()}`
- Generated at: `{generated}`

## Local commands and services

- UNKNOWN — discover only when required by the plan.
- Do not copy credentials, `.env` values, tokens, keys, cookies, or certificates here.

## Health checks, switching, and rollback

- UNKNOWN — a critical live-operation plan must resolve these before readiness.

## Permission and push-trigger implications

- Git capability probe: required before planning isolation.
- Push-trigger implications: UNKNOWN. PlanAnvil does not push by default.
"""

    pursue = repo / ".pursue"
    pursue.mkdir(exist_ok=True)
    atomic_write_text(pursue / "SYSTEM_PROFILE.md", profile)
    atomic_write_text(pursue / "SYSTEM_PROFILE.local.md", local_profile)
    ignore_changed = append_ignore_rules(
        repo,
        [
            ".pursue/SYSTEM_PROFILE.local.md",
            ".pursue/runs/*/local-state.json",
            ".pursue/runs/*/.generation-lock",
            ".pursue/runs/*/.execution-lock",
        ],
    )
    return {
        "ok": True,
        "result": "PROFILE_READY",
        "repository_profile": ".pursue/SYSTEM_PROFILE.md",
        "local_profile": ".pursue/SYSTEM_PROFILE.local.md",
        "profile_status": "VALID_WITH_UNKNOWNS",
        "ignore_rules_changed": ignore_changed,
        "fingerprint": fingerprint,
        "evidence_sha": head,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create PlanAnvil repository and local profiles")
    parser.add_argument("--planning", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    return emit(profile_repository(args.planning, args.source))


if __name__ == "__main__":
    cli_main(main)
