from __future__ import annotations

import re

_CONTROL_FILES = {
    ".gitignore",
    ".pursue/SYSTEM_PROFILE.md",
}

_RUN_EXACT_FILES = {
    "PLAN.md",
    "manifest.json",
    "state.json",
    "compliance.json",
    "traceability.json",
    "evidence/original-goal.md",
    "evidence/git-capability.json",
    "evidence/lifecycle.json",
    "evidence/instruction-map.json",
    "evidence/analysis.md",
    "evidence/analysis.json",
    "reports/validation/artifacts.json",
    "reports/validation/plan.json",
    "reports/validation/diff.json",
    "reports/validation/summary.json",
    "reports/plan-review/review-bundle.json",
    "reports/plan-review/review-prompt.md",
    "reports/plan-review/blind-review.md",
    "reports/plan-review/blind-review.json",
    "reports/plan-review/comparison.json",
    "final/REPORT.md",
}

_RUN_ROLE_PATTERNS = [
    re.compile(r"^stages/STAGE-[0-9]{2}[A-Z]?\.md$"),
    re.compile(r"^risks/RISK-[0-9]{2}[A-Z]?-[0-9]{2}\.json$"),
    re.compile(r"^checkpoints/CHECKPOINT-[A-Za-z0-9][A-Za-z0-9._-]*\.json$"),
]

_LOCAL_ONLY_NAMES = {
    "local-state.json",
    ".generation-lock",
    ".execution-lock",
}


def allowed_planning_path(path: str, run_rel: str) -> bool:
    """Return whether a repository-relative path has a defined planning role."""
    normalized = path.replace("\\", "/").lstrip("./")
    normalized_run = run_rel.replace("\\", "/").strip("/")
    if normalized in _CONTROL_FILES:
        return True
    prefix = normalized_run + "/"
    if not normalized.startswith(prefix):
        return False
    relative = normalized[len(prefix):]
    if (
        relative in _LOCAL_ONLY_NAMES
        or relative.startswith(".")
        or "/." in relative
    ):
        return False
    if relative in _RUN_EXACT_FILES:
        return True
    return any(pattern.fullmatch(relative) for pattern in _RUN_ROLE_PATTERNS)


def allowed_run_artifacts(run_rel: str) -> list[str]:
    """Return the human-readable exact policy used in validation reports."""
    prefix = run_rel.replace("\\", "/").strip("/")
    exact = [f"{prefix}/{path}" for path in sorted(_RUN_EXACT_FILES)]
    patterns = [
        f"{prefix}/stages/STAGE-<ID>.md",
        f"{prefix}/risks/RISK-<ID>.json",
        f"{prefix}/checkpoints/CHECKPOINT-<ID>.json",
    ]
    return [*sorted(_CONTROL_FILES), *exact, *patterns]
