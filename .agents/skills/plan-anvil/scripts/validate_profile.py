from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from common import cli_main, discover_repo, emit, is_ignored, is_tracked, privacy_findings, sha256_file


REQUIRED_REPOSITORY_HEADINGS = [
    "# PlanAnvil Repository Profile",
    "## Repository structure and architecture",
    "## Languages, runtimes, and dependency managers",
    "## Build, test, lint, and static-analysis commands",
    "## Git conventions and quality gates",
    "## Project instruction map",
    "## Deployment, state, and rollback rules",
    "## Risk and activation policy",
    "## Evidence and freshness",
]

REQUIRED_LOCAL_HEADINGS = [
    "# PlanAnvil Local Profile",
    "## Local commands and services",
    "## Health checks, switching, and rollback",
    "## Permission and push-trigger implications",
]


def validate_profile(planning: Path) -> dict[str, Any]:
    repo = discover_repo(planning)
    profile = repo / ".pursue/SYSTEM_PROFILE.md"
    local = repo / ".pursue/SYSTEM_PROFILE.local.md"
    findings: list[dict[str, Any]] = []

    if not profile.is_file():
        findings.append({"kind": "missing", "path": ".pursue/SYSTEM_PROFILE.md"})
    if not local.is_file():
        findings.append({"kind": "missing", "path": ".pursue/SYSTEM_PROFILE.local.md"})

    if profile.is_file():
        text = profile.read_text(encoding="utf-8")
        for heading in REQUIRED_REPOSITORY_HEADINGS:
            if heading not in text:
                findings.append({"kind": "missing-heading", "path": ".pursue/SYSTEM_PROFILE.md", "heading": heading})
        status_match = re.search(r"(?m)^- Profile status: `([^`]+)`$", text)
        if not status_match or status_match.group(1) not in {"VALID", "VALID_WITH_UNKNOWNS", "PARTIALLY_STALE", "STALE", "UNVERIFIABLE"}:
            findings.append({"kind": "invalid-profile-status", "path": ".pursue/SYSTEM_PROFILE.md"})
        elif status_match.group(1) in {"STALE", "UNVERIFIABLE"}:
            findings.append({"kind": "blocking-profile-status", "path": ".pursue/SYSTEM_PROFILE.md", "status": status_match.group(1)})
        instruction_section = re.search(r"(?ms)^## Project instruction map\n(.*?)(?=^## |\Z)", text)
        if instruction_section is None:
            findings.append({"kind": "missing-instruction-map-section", "path": ".pursue/SYSTEM_PROFILE.md"})
        else:
            body = instruction_section.group(1)
            if "Pending explicit instruction mapping" in body or not re.search(r"(?m)^- `[^`]+` \(`sha256:[0-9a-f]{64}`\)", body):
                findings.append({"kind": "unresolved-instruction-map", "path": ".pursue/SYSTEM_PROFILE.md"})
        hash_entries = re.findall(r"(?m)^- `([^`]+)`: `(sha256:[0-9a-f]{64})`$", text)
        for relative, expected in hash_entries:
            candidate = repo / relative
            try:
                candidate.resolve().relative_to(repo.resolve())
            except ValueError:
                findings.append({"kind": "profile-evidence-path-escape", "path": relative})
                continue
            if not candidate.is_file():
                findings.append({"kind": "profile-evidence-missing", "path": relative})
            elif sha256_file(candidate) != expected:
                findings.append({"kind": "profile-evidence-stale", "path": relative})
        for item in privacy_findings(Path(".pursue/SYSTEM_PROFILE.md"), text):
            findings.append(item)

    if local.is_file():
        text = local.read_text(encoding="utf-8")
        for heading in REQUIRED_LOCAL_HEADINGS:
            if heading not in text:
                findings.append({"kind": "missing-heading", "path": ".pursue/SYSTEM_PROFILE.local.md", "heading": heading})
        secret_findings = [item for item in privacy_findings(Path(".pursue/SYSTEM_PROFILE.local.md"), text) if item["kind"] != "absolute-path"]
        findings.extend(secret_findings)
        if not is_ignored(repo, local):
            findings.append({"kind": "not-ignored", "path": ".pursue/SYSTEM_PROFILE.local.md"})
        if is_tracked(repo, local):
            findings.append({"kind": "tracked-local-state", "path": ".pursue/SYSTEM_PROFILE.local.md"})

    return {
        "ok": not findings,
        "result": "PASS" if not findings else "FAIL",
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate PlanAnvil repository and local profiles")
    parser.add_argument("--planning", type=Path, default=Path.cwd())
    args = parser.parse_args()
    payload = validate_profile(args.planning)
    return emit(payload, exit_code=0 if payload["ok"] else 2)


if __name__ == "__main__":
    cli_main(main)
