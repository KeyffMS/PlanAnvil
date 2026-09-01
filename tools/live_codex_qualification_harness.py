from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import live_codex_qualification as base


TARGET_CAPABILITIES = {"C01", "C05", "C09", "C14"}
_ORIGINAL_CAPABILITY_RUNTIME = base.capability_runtime


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _copytree(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _install_plananvil_release(root: Path, repo: Path) -> None:
    completed = base.run(
        [
            sys.executable,
            "tools/plananvil_dist.py",
            "install",
            "--target",
            str(repo.resolve()),
        ],
        cwd=root,
        check=False,
        timeout=120,
    )
    if completed.returncode != 0:
        raise base.QualificationError(
            "PlanAnvil fixture installation failed: "
            + base.sanitize_text((completed.stderr or completed.stdout)[-2000:])
        )


def _run_trial(
    *,
    capability_id: str,
    trial: dict[str, Any],
    cwd: Path,
    snapshot_repo: Path,
    schemas: dict[str, Path],
    results_dir: Path,
    position: int,
    add_dir: Path | None = None,
    timeout: int = 600,
) -> dict[str, Any]:
    before = base.git_snapshot(snapshot_repo)
    output = results_dir / f"trial-{position:02d}.json"
    payload, events, error = base.run_codex(
        cwd=cwd,
        prompt=base.trial_prompt(capability_id, trial),
        schema=schemas["trial"],
        output=output,
        sandbox=trial["sandbox"],
        add_dir=add_dir,
        trust_project=True,
        hook_trust=True,
        ignore_rules=False,
        timeout=timeout,
    )
    after = base.git_snapshot(snapshot_repo)
    if error:
        payload = {
            "capability_id": capability_id,
            "trial": trial["name"],
            "outcome": "BLOCKED",
            "assertions": [],
            "observations": [error],
            "blocker": error,
        }
    if payload.get("capability_id") != capability_id:
        payload = {
            "capability_id": capability_id,
            "trial": trial["name"],
            "outcome": "BLOCKED",
            "assertions": [],
            "observations": ["trial output capability_id mismatch"],
            "blocker": "trial output capability_id mismatch",
        }
    payload["trial_name"] = trial["name"]
    payload["sandbox"] = trial["sandbox"]
    payload["event_summary"] = events
    payload["git_before"] = before
    payload["git_after"] = after
    return base.sanitize(payload)


def _evaluate_and_write(
    *,
    root: Path,
    cap_runtime: Path,
    capability_id: str,
    cap_dir: Path,
    trial_payloads: list[dict[str, Any]],
    fixture_commit: str,
    schemas: dict[str, Path],
    results_dir: Path,
    evaluator_dir: Path,
    version: str,
    os_name: str,
    source_commit: str,
    date: str,
) -> tuple[str, bool]:
    base.prepare_evaluator_repo(
        evaluator_dir,
        expected=cap_dir / "expected.json",
        trial_payloads=trial_payloads,
    )
    eval_output = results_dir / "evaluation.json"
    evaluation, evaluation_events, evaluation_error = base.run_codex(
        cwd=evaluator_dir,
        prompt=base.evaluator_prompt(capability_id),
        schema=schemas["evaluation"],
        output=eval_output,
        sandbox="read-only",
        trust_project=False,
        hook_trust=False,
        ignore_rules=True,
        timeout=600,
    )
    if evaluation_error:
        result = "BLOCKED"
        expected_met = False
        observations = [f"Evaluation invocation failed: {evaluation_error}"]
        blocker = evaluation_error
        summary = f"{capability_id} blocked during evidence evaluation."
    elif evaluation.get("capability_id") != capability_id:
        result = "BLOCKED"
        expected_met = False
        observations = ["Evaluator capability_id mismatch."]
        blocker = "Evaluator capability_id mismatch."
        summary = f"{capability_id} blocked because evaluator output was invalid."
    else:
        result = str(evaluation.get("result"))
        expected_met = bool(evaluation.get("expected_met"))
        observations = list(evaluation.get("observations") or [])
        blocker = evaluation.get("blocker")
        summary = str(evaluation.get("summary") or "")
        if result == "REPRODUCED" and (not expected_met or blocker):
            result = "BLOCKED"
            expected_met = False
            blocker = "Evaluator returned an internally inconsistent REPRODUCED decision."
            observations.append(blocker)
    trial_payloads.append({"evaluator_event_summary": evaluation_events})
    required = base.write_evidence(
        root=root,
        capability_id=capability_id,
        result=result,
        expected_met=expected_met,
        observations=observations,
        blocker=blocker,
        summary=summary,
        trials=trial_payloads,
        fixture_commit=fixture_commit,
        version=version,
        os_name=os_name,
        source_commit=source_commit,
        date=date,
    )
    base.local_commit(root, capability_id)
    shutil.rmtree(cap_runtime, ignore_errors=True)
    return result, required


def _runtime_paths(
    *,
    root: Path,
    runtime_root: Path,
    capability_id: str,
) -> tuple[Path, Path, Path, Path, Path, Path, Path]:
    cap_dir = root / "capabilities" / capability_id
    cap_runtime = runtime_root / capability_id
    if cap_runtime.exists():
        shutil.rmtree(cap_runtime)
    spec_dir = cap_runtime / "spec"
    repo = cap_runtime / "repo"
    worktrees = cap_runtime / "worktrees"
    results_dir = cap_runtime / "results"
    evaluator_dir = cap_runtime / "evaluator"
    worktrees.mkdir(parents=True)
    results_dir.mkdir(parents=True)
    base.copy_spec(cap_dir, spec_dir)
    return cap_dir, cap_runtime, spec_dir, repo, worktrees, results_dir, evaluator_dir


def _c01_runtime(
    *,
    root: Path,
    runtime_root: Path,
    schemas: dict[str, Path],
    version: str,
    os_name: str,
    source_commit: str,
    date: str,
) -> tuple[str, bool]:
    capability_id = "C01"
    cap_dir, cap_runtime, spec_dir, repo, worktrees, results_dir, evaluator_dir = _runtime_paths(
        root=root, runtime_root=runtime_root, capability_id=capability_id
    )
    base.ensure_git_repo(repo)
    skill = repo / ".agents" / "skills" / "fixture-capability" / "SKILL.md"
    _write(
        skill,
        """---
name: fixture-capability
description: Repository qualification fixture. Use only when explicitly invoked as $fixture-capability.
---

# Fixture capability

When this skill is explicitly invoked, treat the literal token `FIXTURE_SKILL_ACTIVE`
as the activation proof. Do not modify files. For a structured caller response,
include `FIXTURE_SKILL_ACTIVE` in the minimal observation that proves this skill was active.
""",
    )
    nested = repo / "nested" / "child"
    _write(nested / "README.md", "Nested working directory for repository skill discovery.\n")
    _write(repo / "README.md", "C01 repository skill discovery fixture.\n")
    fixture_commit = base.commit_fixture_baseline(repo)
    trials = [
        {
            "name": "explicit_repository_skill_activation",
            "sandbox": "read-only",
            "prompt": (
                "Explicitly invoke $fixture-capability from the repository root. "
                "Do not infer activation merely by reading SKILL.md directly. "
                "Exercise Codex repository skill resolution and report PASS only if the "
                "fixture skill is resolved as a repository skill and its activation proof "
                "FIXTURE_SKILL_ACTIVE is present."
            ),
        },
        {
            "name": "nested_working_directory_discovery",
            "sandbox": "read-only",
            "prompt": (
                "You are starting from a nested working directory inside the same Git repository. "
                "Run `git rev-parse --show-toplevel` only to verify repository identity without "
                "reporting the absolute path. Then explicitly invoke $fixture-capability. "
                "Report PASS only if the repository skill is discovered from this nested start "
                "and the activation proof FIXTURE_SKILL_ACTIVE is present."
            ),
        },
    ]
    payloads = [
        _run_trial(
            capability_id=capability_id,
            trial=trials[0],
            cwd=repo,
            snapshot_repo=repo,
            schemas=schemas,
            results_dir=results_dir,
            position=1,
        ),
        _run_trial(
            capability_id=capability_id,
            trial=trials[1],
            cwd=nested,
            snapshot_repo=repo,
            schemas=schemas,
            results_dir=results_dir,
            position=2,
        ),
    ]
    return _evaluate_and_write(
        root=root,
        cap_runtime=cap_runtime,
        capability_id=capability_id,
        cap_dir=cap_dir,
        trial_payloads=payloads,
        fixture_commit=fixture_commit,
        schemas=schemas,
        results_dir=results_dir,
        evaluator_dir=evaluator_dir,
        version=version,
        os_name=os_name,
        source_commit=source_commit,
        date=date,
    )


def _seed_c05(repo: Path) -> None:
    plan = repo / "PLAN.md"
    _write(plan, "# C05 immutable review plan\n\nReview this exact fixture.\n")
    plan_hash = _sha256(plan)
    bundle = repo / "review-bundle.json"
    bundle_payload = {
        "schema_version": "fixture-1",
        "goal": "Review fixture only",
        "files": {"PLAN.md": f"sha256:{plan_hash}"},
    }
    _write(bundle, json.dumps(bundle_payload, indent=2, sort_keys=True) + "\n")
    _write(repo / "review-bundle.sha256", f"{_sha256(bundle)}  review-bundle.json\n")
    _write(repo / "README.md", "C05 immutable reviewer handoff fixture.\n")


def _c05_runtime(
    *,
    root: Path,
    runtime_root: Path,
    schemas: dict[str, Path],
    version: str,
    os_name: str,
    source_commit: str,
    date: str,
) -> tuple[str, bool]:
    capability_id = "C05"
    cap_dir, cap_runtime, spec_dir, repo, worktrees, results_dir, evaluator_dir = _runtime_paths(
        root=root, runtime_root=runtime_root, capability_id=capability_id
    )
    base.ensure_git_repo(repo)
    _seed_c05(repo)
    fixture_commit = base.commit_fixture_baseline(repo)
    baseline = fixture_commit
    trials = [
        {
            "name": "fresh_explicit_bundle",
            "sandbox": "read-only",
            "prompt": (
                "Act as the reviewer receiving only the explicit path `review-bundle.json`. "
                "First verify its recorded bundle digest in review-bundle.sha256, then read only "
                "the files explicitly named by the verified bundle and verify their recorded hashes. "
                "Report PASS only if the immutable explicit handoff is accepted."
            ),
        },
        {
            "name": "stale_bundle_rejected",
            "sandbox": "workspace-write",
            "prompt": (
                "Exercise the stale-bundle case explicitly. Modify PLAN.md without changing "
                "review-bundle.json or review-bundle.sha256. Then process the same explicit bundle. "
                "The bundle itself must still match its recorded bundle digest, but its recorded "
                "PLAN.md hash must now be stale. Reject the handoff as STALE and report PASS for "
                "the expected rejection only if the stale target hash is actually detected."
            ),
        },
        {
            "name": "changed_bundle_rejected",
            "sandbox": "workspace-write",
            "prompt": (
                "Exercise the changed-bundle case. Modify review-bundle.json without updating "
                "review-bundle.sha256, then attempt the explicit handoff. Reject it before trusting "
                "its file list because the bundle digest no longer matches."
            ),
        },
        {
            "name": "missing_bundle_rejected",
            "sandbox": "workspace-write",
            "prompt": (
                "Exercise the missing-bundle case. Remove review-bundle.json and then attempt the "
                "explicit handoff. Reject it because the required immutable bundle is missing."
            ),
        },
        {
            "name": "escaped_bundle_rejected",
            "sandbox": "read-only",
            "prompt": (
                "Exercise path escape rejection using candidate bundle path `../spec/expected.json`. "
                "Canonicalize/check the candidate against the current repository boundary first and "
                "reject it as escaped without opening or trusting the outside file."
            ),
        },
    ]
    payloads: list[dict[str, Any]] = []
    for position, trial in enumerate(trials, start=1):
        base.reset_fixture(repo, baseline, worktrees)
        payloads.append(
            _run_trial(
                capability_id=capability_id,
                trial=trial,
                cwd=repo,
                snapshot_repo=repo,
                schemas=schemas,
                results_dir=results_dir,
                position=position,
                add_dir=worktrees if trial["sandbox"] == "workspace-write" else None,
            )
        )
    return _evaluate_and_write(
        root=root,
        cap_runtime=cap_runtime,
        capability_id=capability_id,
        cap_dir=cap_dir,
        trial_payloads=payloads,
        fixture_commit=fixture_commit,
        schemas=schemas,
        results_dir=results_dir,
        evaluator_dir=evaluator_dir,
        version=version,
        os_name=os_name,
        source_commit=source_commit,
        date=date,
    )


def _hook_proxy_source() -> str:
    return r"""from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

event_name, script_name = sys.argv[1], sys.argv[2]
payload = sys.stdin.read()
root = Path(subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"], text=True
).strip())
script = root / ".codex" / "hooks" / script_name
completed = subprocess.run(
    [sys.executable, str(script)],
    input=payload,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=False,
)
record = {"event": event_name, "returncode": completed.returncode}
try:
    parsed = json.loads(completed.stdout) if completed.stdout.strip() else {}
except json.JSONDecodeError:
    parsed = {}
if isinstance(parsed, dict):
    if "continue" in parsed:
        record["continue"] = parsed.get("continue")
    hook_output = parsed.get("hookSpecificOutput")
    if isinstance(hook_output, dict) and hook_output.get("additionalContext"):
        record["additional_context"] = True
log = root / ".pursue" / "qualification-hook-events.jsonl"
log.parent.mkdir(parents=True, exist_ok=True)
with log.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
sys.stdout.write(completed.stdout)
sys.stderr.write(completed.stderr)
raise SystemExit(completed.returncode)
"""


def _instrument_c09_hooks(repo: Path) -> None:
    hooks_path = repo / ".codex" / "hooks.json"
    hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
    mapping = {
        "PreCompact": "plan-anvil-compaction.py",
        "PostCompact": "plan-anvil-recovery.py",
        "SessionStart": "plan-anvil-recovery.py",
    }
    for event_name, script_name in mapping.items():
        groups = hooks.get("hooks", {}).get(event_name, [])
        for group in groups:
            for handler in group.get("hooks", []):
                handler["command"] = (
                    'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/'
                    f'qualification-hook-proxy.py" {event_name} {script_name}'
                )
    _write(hooks_path, json.dumps(hooks, indent=2, sort_keys=True) + "\n")
    _write(repo / ".codex" / "hooks" / "qualification-hook-proxy.py", _hook_proxy_source())
    config_path = repo / ".codex" / "config.toml"
    existing_config = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    if "model_auto_compact_token_limit" not in existing_config:
        existing_config = "model_auto_compact_token_limit = 5000\n\n" + existing_config
    _write(config_path, existing_config)
    with (repo / ".gitignore").open("a", encoding="utf-8") as handle:
        handle.write("\n.pursue/qualification-hook-events.jsonl\n")
    payload_dir = repo / "qualification-payload"
    payload_dir.mkdir(parents=True, exist_ok=True)
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for index in range(1, 13):
        text = (f"SEGMENT-{index:02d}-" + alphabet * 20 + "\n") * 4
        _write(payload_dir / f"segment-{index:02d}.txt", text)


def _parse_json_stdout(completed: subprocess.CompletedProcess[str], label: str) -> dict[str, Any]:
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise base.QualificationError(f"{label} returned invalid JSON: {exc}") from exc
    if not isinstance(value, dict) or not value.get("ok"):
        raise base.QualificationError(f"{label} failed: {base.sanitize_text(completed.stdout[-2000:])}")
    return value


def _prepare_c09_active_run(root: Path, repo: Path, worktrees: Path, version: str) -> tuple[Path, str]:
    _install_plananvil_release(root, repo)
    _instrument_c09_hooks(repo)
    _write(repo / "README.md", "C09 genuine auto-compaction fixture.\n")
    base.git(repo, "add", "-A")
    base.git(repo, "commit", "--allow-empty", "-q", "-m", "Install PlanAnvil C09 fixture")
    destination = worktrees / "planning"
    start = base.run(
        [
            sys.executable,
            ".agents/skills/plan-anvil/scripts/plan_anvil.py",
            "start",
            "--source",
            ".",
            "--destination",
            str(destination),
            "--goal",
            "Qualify checkpoint compaction recovery without a permanent loop",
            "--codex-version",
            version,
            "--model",
            base.MODEL,
            "--permission-mode",
            "approval=never; sandbox=workspace-write",
            "--project-trust",
            "TRUSTED",
            "--hook-mode",
            "HOOKS_TRUSTED",
        ],
        cwd=repo,
        check=False,
        timeout=240,
    )
    payload = _parse_json_stdout(start, "PlanAnvil start")
    planning = Path(payload["planning_worktree"]).resolve()
    run_root = str(payload["run_root"])
    checkpoint = base.run(
        [
            sys.executable,
            ".agents/skills/plan-anvil/scripts/create_generation_checkpoint.py",
            "--planning",
            ".",
            "--run-root",
            run_root,
        ],
        cwd=planning,
        check=False,
        timeout=120,
    )
    _parse_json_stdout(checkpoint, "generation checkpoint")
    return planning, run_root


def _c09_runtime(
    *,
    root: Path,
    runtime_root: Path,
    schemas: dict[str, Path],
    version: str,
    os_name: str,
    source_commit: str,
    date: str,
) -> tuple[str, bool]:
    capability_id = "C09"
    cap_dir, cap_runtime, spec_dir, repo, worktrees, results_dir, evaluator_dir = _runtime_paths(
        root=root, runtime_root=runtime_root, capability_id=capability_id
    )
    base.ensure_git_repo(repo)
    planning, run_root = _prepare_c09_active_run(root, repo, worktrees, version)
    fixture_commit = base.git(repo, "rev-parse", "HEAD")
    trial = {
        "name": "checkpoint_auto_compact_recover_recompact",
        "sandbox": "workspace-write",
        "prompt": (
            "A real PlanAnvil planning run and a schema-valid generation checkpoint are already "
            f"present at run root `{Path(run_root).name}`. Do NOT invoke hook scripts directly and "
            "do NOT simulate hook events. Exercise genuine Codex automatic compaction. Read the "
            "files qualification-payload/segment-01.txt through segment-12.txt one at a time with "
            "separate shell-tool calls. After every two segments, inspect "
            ".pursue/qualification-hook-events.jsonl and continue until it records at least two "
            "PreCompact and two PostCompact events, or until all segments are consumed. After each "
            "observed compaction, continue normal tool use, read state.json plus the checkpoint "
            "named by last_checkpoint, and reconcile `git status --porcelain` and `git rev-parse HEAD`. "
            "PASS only if the valid checkpoint allowed genuine compaction, recovery context let the "
            "session continue with canonical state/Git coherent, and a second genuine compaction also "
            "completed without a permanent stop loop. Report event counts, booleans, and relative "
            "run/checkpoint paths only; never report absolute paths."
        ),
    }
    payload = _run_trial(
        capability_id=capability_id,
        trial=trial,
        cwd=planning,
        snapshot_repo=planning,
        schemas=schemas,
        results_dir=results_dir,
        position=1,
        add_dir=worktrees,
        timeout=900,
    )
    return _evaluate_and_write(
        root=root,
        cap_runtime=cap_runtime,
        capability_id=capability_id,
        cap_dir=cap_dir,
        trial_payloads=[payload],
        fixture_commit=fixture_commit,
        schemas=schemas,
        results_dir=results_dir,
        evaluator_dir=evaluator_dir,
        version=version,
        os_name=os_name,
        source_commit=source_commit,
        date=date,
    )


def _prepare_c14_source(root: Path, source: Path) -> str:
    source.mkdir(parents=True, exist_ok=True)
    _write(source / "source.txt", "C14 source immutability sentinel.\n")
    _write(source / "README.md", "C14 isolated planning worktree fixture.\n")
    base.ensure_git_repo(source)
    branch = base.git(source, "branch", "--show-current", check=False)
    if not branch:
        base.git(source, "switch", "-c", "main")
    elif branch != "main":
        base.git(source, "branch", "-m", "main")
    _install_plananvil_release(root, source)
    base.git(source, "add", "-A")
    base.git(source, "commit", "--allow-empty", "-q", "-m", "Install PlanAnvil C14 fixture")
    return base.git(source, "rev-parse", "HEAD")


def _c14_runtime(
    *,
    root: Path,
    runtime_root: Path,
    schemas: dict[str, Path],
    version: str,
    os_name: str,
    source_commit: str,
    date: str,
) -> tuple[str, bool]:
    capability_id = "C14"
    cap_dir, cap_runtime, spec_dir, repo, worktrees, results_dir, evaluator_dir = _runtime_paths(
        root=root, runtime_root=runtime_root, capability_id=capability_id
    )
    base.ensure_git_repo(repo)
    _write(repo / "README.md", "C14 command-driver repository.\n")
    base.commit_fixture_baseline(repo)
    source = worktrees / "source"
    fixture_commit = _prepare_c14_source(root, source)
    destination = worktrees / "planning"
    trial = {
        "name": "planning_worktree_isolation",
        "sandbox": "workspace-write",
        "prompt": (
            "Exercise PlanAnvil bootstrap against the disposable source repository at "
            "`../worktrees/source`; this path is the intentionally writable qualification Git root. "
            "Before starting, record booleans/hashes for source branch, HEAD, index tree, status, and "
            "source.txt. Run the real deterministic controller:\n"
            "`python ../worktrees/source/.agents/skills/plan-anvil/scripts/plan_anvil.py start "
            "--source ../worktrees/source --destination ../worktrees/planning "
            f"--goal 'Qualify planning isolation' --codex-version '{version}' "
            "--model 'gpt-5.6-sol' --permission-mode 'approval=never; sandbox=workspace-write' "
            "--project-trust TRUSTED --hook-mode HOOKS_UNAVAILABLE`.\n"
            "Parse its JSON result. Then verify the source branch/HEAD/index/status/source.txt are "
            "unchanged, the reported planning branch is distinct, the linked planning worktree exists "
            "at ../worktrees/planning, and PlanAnvil planning/scaffold changes exist only there. "
            "Do not edit the source repository manually and do not use danger-full-access."
        ),
    }
    payload = _run_trial(
        capability_id=capability_id,
        trial=trial,
        cwd=repo,
        snapshot_repo=source,
        schemas=schemas,
        results_dir=results_dir,
        position=1,
        add_dir=worktrees,
        timeout=600,
    )
    source_after = base.git_snapshot(source)
    planning_exists = destination.is_dir()
    planning_branch = (
        base.git(destination, "branch", "--show-current", check=False) if planning_exists else ""
    )
    planning_status = (
        base.git(destination, "status", "--porcelain=v1", "--untracked-files=all", check=False).splitlines()
        if planning_exists
        else []
    )
    payload.setdefault("observations", [])
    payload["observations"].extend(
        [
            f"outer_source_head={source_after.get('head')}",
            f"outer_source_branch={source_after.get('branch')}",
            f"outer_planning_worktree_exists={str(planning_exists).lower()}",
            f"outer_planning_branch_distinct={str(bool(planning_branch and planning_branch != source_after.get('branch'))).lower()}",
            f"outer_planning_changes_present={str(bool(planning_status)).lower()}",
        ]
    )
    return _evaluate_and_write(
        root=root,
        cap_runtime=cap_runtime,
        capability_id=capability_id,
        cap_dir=cap_dir,
        trial_payloads=[base.sanitize(payload)],
        fixture_commit=fixture_commit,
        schemas=schemas,
        results_dir=results_dir,
        evaluator_dir=evaluator_dir,
        version=version,
        os_name=os_name,
        source_commit=source_commit,
        date=date,
    )


def capability_runtime(**kwargs: Any) -> tuple[str, bool]:
    capability_id = str(kwargs["capability_id"])
    if capability_id not in TARGET_CAPABILITIES:
        return _ORIGINAL_CAPABILITY_RUNTIME(**kwargs)
    common = {key: value for key, value in kwargs.items() if key != "capability_id"}
    if capability_id == "C01":
        return _c01_runtime(**common)
    if capability_id == "C05":
        return _c05_runtime(**common)
    if capability_id == "C09":
        return _c09_runtime(**common)
    return _c14_runtime(**common)


def main(argv: list[str] | None = None) -> int:
    base.capability_runtime = capability_runtime
    return base.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
