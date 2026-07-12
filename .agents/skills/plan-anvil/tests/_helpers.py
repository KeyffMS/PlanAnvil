from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from common import atomic_write_json, load_json, make_plan_id, slugify
from create_planning_worktree import create_planning_worktree
from profile_repository import profile_repository
from record_analysis import record_analysis
from scaffold_run import scaffold_run
from seal_artifacts import seal_artifacts
from test_git_capabilities import probe_git_capabilities
from transition_state import transition_state


def run(*args: str, cwd: Path, check: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(args),
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"command failed: {args}\nstdout={result.stdout}\nstderr={result.stderr}")
    return result


def init_repo(path: Path, *, files: dict[str, str] | None = None, identity: bool = True) -> Path:
    path.mkdir(parents=True)
    run("git", "init", "-b", "main", cwd=path)
    if identity:
        run("git", "config", "user.name", "PlanAnvil Test", cwd=path)
        run("git", "config", "user.email", "plananvil@example.invalid", cwd=path)
    run("git", "config", "commit.gpgsign", "false", cwd=path)
    defaults = {
        "README.md": "# Fixture\n",
        "AGENTS.md": "# Instructions\n\n- Run tests before committing.\n- Never expose secrets.\n",
        "src/app.py": "def value():\n    return 1\n",
        "tests/test_app.py": "def test_value():\n    assert True\n",
    }
    for rel, content in (files or defaults).items():
        target = path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
    run("git", "add", ".", cwd=path)
    run("git", "commit", "-m", "fixture", cwd=path)
    return path


def cleanup_worktree(source: Path, planning: Path, branch: str) -> None:
    if planning.exists():
        run("git", "worktree", "remove", "--force", str(planning), cwd=source, check=False)
    run("git", "branch", "-D", branch, cwd=source, check=False)


def start_fixture(tmp: Path, goal: str = "Reject an empty display name") -> dict[str, Any]:
    source = init_repo(tmp / "source")
    plan_id = make_plan_id()
    slug = slugify(goal)
    probe = probe_git_capabilities(source, f"test-{plan_id}", tmp / "probes")
    assert probe["ok"], probe
    planning_info = create_planning_worktree(
        source,
        plan_id=plan_id,
        slug=slug,
        capability_report=probe,
        destination=tmp / "planning",
    )
    planning = Path(planning_info["planning_worktree"])
    profile_repository(planning, source)
    scaffold = scaffold_run(
        planning,
        source,
        plan_id=plan_id,
        run_id=planning_info["run_id"],
        slug=slug,
        goal=goal,
        base_branch=planning_info["base_branch"],
        base_sha=planning_info["base_sha"],
        capability_report=probe,
    )
    return {
        "source": source,
        "planning": planning,
        "branch": planning_info["planning_branch"],
        "run_root": planning / scaffold["run_root"],
        "plan_id": plan_id,
        "run_id": planning_info["run_id"],
    }


def author_valid_plan(context: dict[str, Any]) -> None:
    run_root: Path = context["run_root"]
    instruction_map = load_json(run_root / "evidence/instruction-map.json")
    analysis_md = context["planning"].parent / f"{context['run_id']}-analysis.md"
    analysis_json = context["planning"].parent / f"{context['run_id']}-analysis.json"
    analysis_md.write_text(
        """# Goal analysis

## Requested outcome

Reject empty display names without changing public API shape.

## Repository evidence

The repository contains one implementation module, focused tests, and applicable instructions.

## Change classification and risk

The change is isolated and low risk.

## Affected paths and boundaries

Only mapped implementation and test paths may change in the later execution run.

## Assumptions

Existing normalization behavior is preserved.

## Unknowns and verification

Whitespace behavior is verified during the expected-red stage and is not a critical unknown.

## Recommended stage boundaries

Use one behavior-changing stage with an independent verifier.
""",
        encoding="utf-8",
        newline="\n",
    )
    atomic_write_json(
        analysis_json,
        {
            "classification": "ISOLATED",
            "risk": "LOW",
            "affected_paths": instruction_map["affected_paths"],
            "evidence": [
                ".pursue/SYSTEM_PROFILE.md",
                f".pursue/runs/{context['run_id']}/evidence/original-goal.md",
                f".pursue/runs/{context['run_id']}/evidence/instruction-map.json",
            ],
            "assumptions": [
                {
                    "text": "The existing validator and focused tests define the affected behavior.",
                    "confidence": "VERIFIED",
                    "evidence": ["src/app.py", "tests/test_app.py"],
                }
            ],
            "unknowns": [
                {
                    "text": "Exact whitespace normalization is confirmed before implementation.",
                    "critical": False,
                    "verification": "Run the focused baseline and inspect current tests.",
                }
            ],
        },
    )
    result = record_analysis(
        context["planning"],
        run_root,
        analysis_markdown=analysis_md,
        analysis_data=analysis_json,
    )
    assert result["ok"], result
    plan_id = context["plan_id"]
    run_id = context["run_id"]
    manifest = load_json(run_root / "manifest.json")
    plan = f"""# Implementation Plan: Empty display name validation

## Identity

- Plan ID: `{plan_id}`
- Run ID: `{run_id}`
- Contract: PlanAnvil 2.1
- Artifact schema: 1.1.0
- Base branch: `{manifest['repository']['base_branch']}`
- Base SHA: `{manifest['repository']['base_sha']}`
- Planning branch: `{manifest['repository']['planning_branch']}`

## Original goal

Reject an empty display name.

## Outcome and definition of done

Empty and whitespace-only names follow the existing normalization policy, valid names remain accepted, and focused automated tests prove the behavior.

## Generator stop boundary

PlanAnvil generates and validates this contract only. It does not modify product code or tests and does not execute a stage.

## Separate execution-run prompt

In a separate Codex run, load this plan and canonical state, reconcile Git and the latest checkpoint, then execute only the next approved stage while preserving every gate.

## Scope

Validation behavior and focused regression tests.

## Exclusions

Public API renaming, UI copy changes, deployment, and data migration.

## Assumptions, unknowns, and evidence

The existing validator and unit-test paths are verified by repository inspection. Whitespace normalization is confirmed during the stage discovery step before changing behavior.

## Applicable instructions

Read and obey the hashed instruction map in `evidence/instruction-map.json`.

## System and change analysis

One validator controls the behavior. No persistent state, network boundary, or deployment flow changes.

## Dependencies and classification

Classification is LOW risk and behavior-changing. The stage depends on the existing green unit-test baseline.

## Stable stage index

- `STAGE-01` — reject empty display names while preserving valid input.

## Traceability

`REQ-01-01 → STAGE-01 → AC-01-01 → RISK-01-01 → CTRL-01-01 → automated test evidence`.

## Testing and independent verification

Run a green baseline, add an expected-red regression test, implement the minimum behavior, run the focused and full suites, then obtain independent read-only verification.

## Git, integration, and control-root rules

Use `pursue/{plan_id}/display-name` for task work and `pursue/integration/{plan_id}/display-name` only when integration is needed. Control artifacts remain in the planning worktree. One modifier acts at a time.

## Production verification, switching, and approvals

No live switch is required. Base-branch merge or push requires explicit user approval.

## Rollback and recovery

Revert the single coherent implementation commit if verification fails. Reconcile canonical state and Git before resuming.

## Resume and reconciliation

Read manifest, state, local state, profiles, instruction map, latest checkpoint, and Git state. Stop on any mismatch.

## Status and next action

- Status: `PLAN_READY`
- Next action: `Start a separate execution run for STAGE-01.`

## Final report requirements

Report tests, independent verification, commit, remaining risks, and approvals. No implementation was executed. Start a separate Codex run using the execution prompt in PLAN.md.
"""
    (run_root / "PLAN.md").write_text(plan, encoding="utf-8", newline="\n")

    instruction = instruction_map["files"][0]
    stage = f"""---
schema_version: "1.1.0"
stage_id: "STAGE-01"
outcome: "Empty display names are rejected consistently."
classification: "BEHAVIOR"
requirements: ["REQ-01-01"]
criteria: ["AC-01-01"]
risks: ["RISK-01-01"]
dependencies: []
applicable_instructions: [{{"path": {instruction["path"]!r}, "sha256": {instruction["sha256"]!r}}}]
allowed_write_paths: ["src/**", "tests/**"]
---

# STAGE-01 — Reject empty display names

## Outcome

The validator rejects empty input without regressing valid names.

## Scope

Validator behavior and focused tests.

## Exclusions

API renaming, UI copy, persistence, and deployment.

## Affected paths or discovery procedure

Confirm the current validator and its nearest tests before editing; write only within the approved paths.

## Applicable instructions

Read every instruction file recorded for the affected paths and verify its hash.

## Dependencies and conflicts

Requires a green baseline. Stop on instruction or behavior conflicts.

## Acceptance criteria

- `AC-01-01`: empty and whitespace-only names follow the verified normalization policy and valid names remain accepted.

## Risks and controls

- `RISK-01-01` is controlled by `CTRL-01-01`, focused regression tests, and the full suite.

## Evidence cycle

GREEN BASELINE → EXPECTED RED → IMPLEMENTATION → FULL GREEN → INDEPENDENT VERIFICATION.

## Modifier and verifier roles

Jenny owns approved tests, one implementation agent owns approved production paths, and the verifier remains read-only.

## Commit and checkpoint

Create one coherent implementation-and-test commit and `CHECKPOINT-01-VERIFIED`.

## Rollback

Revert the stage commit and restore the preceding valid checkpoint.
"""
    (run_root / "stages/STAGE-01.md").write_text(stage, encoding="utf-8", newline="\n")

    traceability = {
        "schema_version": "1.1.0",
        "requirements": [
            {
                "id": "REQ-01-01",
                "text": "The validator rejects empty display names without rejecting valid names.",
                "critical": True,
                "stages": ["STAGE-01"],
                "criteria": ["AC-01-01"],
            }
        ],
        "criteria": [
            {
                "id": "AC-01-01",
                "stage": "STAGE-01",
                "risks": ["RISK-01-01"],
                "controls": ["CTRL-01-01"],
                "evidence_type": "AUTOMATED_TEST",
                "evidence": [],
            }
        ],
        "controls": [
            {
                "id": "CTRL-01-01",
                "description": "Focused regression and full-suite verification.",
                "verification": "Expected-red failure followed by focused and full green results.",
            }
        ],
        "gaps": [],
    }
    atomic_write_json(run_root / "traceability.json", traceability)

    risk = {
        "schema_version": "1.1.0",
        "id": "RISK-01-01",
        "stage": "STAGE-01",
        "level": "LOW",
        "description": "Normalization could reject valid names.",
        "source": "Repository analysis",
        "affected_components": ["validator"],
        "probability": "LOW",
        "impact": "MEDIUM",
        "detection": ["CTRL-01-01"],
        "criteria": ["AC-01-01"],
        "controls": ["CTRL-01-01"],
        "mitigation": "Preserve verified normalization and test valid examples.",
        "rollback": "Revert the stage commit.",
        "status": "OPEN",
    }
    atomic_write_json(run_root / "risks/RISK-01-01.json", risk)

    sealed = seal_artifacts(context["planning"], run_root)
    assert sealed["ok"], sealed
