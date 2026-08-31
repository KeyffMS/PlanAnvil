from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

CAPABILITY_IDS = [f"C{i:02d}" for i in range(1, 17)]
MODEL = "gpt-5.6-sol"
SESSION_ID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
PRIVATE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])/(?:home|Users|private|var|tmp|opt|srv|mnt|Volumes|qualification)/[^\s`\"'<>]+"
)
TOKEN_RE = re.compile(r"\b(?:sk|gh[pousr])_[A-Za-z0-9_-]{16,}\b")
CAP_ID_RE = re.compile(r"^C(?:0[1-9]|1[0-6])$")


class QualificationError(RuntimeError):
    pass


def run(
    args: list[str],
    *,
    cwd: Path,
    check: bool = True,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if check and completed.returncode != 0:
        stderr = sanitize_text(completed.stderr[-4000:])
        raise QualificationError(f"{args[0]} exited {completed.returncode}: {stderr}")
    return completed


def git(repo: Path, *args: str, check: bool = True) -> str:
    return run(["git", *args], cwd=repo, check=check, timeout=60).stdout.strip()


def json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sanitize_text(value: str) -> str:
    value = TOKEN_RE.sub("<REDACTED_TOKEN>", value)
    value = SESSION_ID_RE.sub("<SESSION_ID>", value)
    value = PRIVATE_PATH_RE.sub("<PATH>", value)
    return value


def sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): sanitize(item) for key, item in value.items()}
    return value


def sha256_tree(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def os_label() -> str:
    os_release = Path("/etc/os-release")
    if os_release.exists():
        data: dict[str, str] = {}
        for line in os_release.read_text(encoding="utf-8").splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key] = value.strip().strip('"')
        if data.get("PRETTY_NAME"):
            return data["PRETTY_NAME"]
    return "Linux"


def codex_version() -> str:
    completed = run(["codex", "--version"], cwd=Path.cwd(), timeout=30)
    value = (completed.stdout or completed.stderr).strip()
    if not value:
        raise QualificationError("codex --version returned no version")
    return sanitize_text(value)


def toml_quote(value: str) -> str:
    return json.dumps(value)


def event_summary(stdout: str) -> dict[str, Any]:
    event_types: collections.Counter[str] = collections.Counter()
    item_types: collections.Counter[str] = collections.Counter()
    completed_commands = 0
    file_changes = 0
    errors = 0
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        if isinstance(event_type, str):
            event_types[event_type] += 1
            if event_type == "error":
                errors += 1
        item = event.get("item")
        if isinstance(item, dict):
            item_type = item.get("type")
            if isinstance(item_type, str):
                item_types[item_type] += 1
                if event_type == "item.completed" and item_type == "command_execution":
                    completed_commands += 1
                if event_type == "item.completed" and item_type == "file_change":
                    file_changes += 1
    return {
        "event_types": dict(sorted(event_types.items())),
        "item_types": dict(sorted(item_types.items())),
        "completed_command_items": completed_commands,
        "completed_file_change_items": file_changes,
        "error_events": errors,
    }


def common_codex_args(
    *,
    cwd: Path,
    sandbox: str,
    schema: Path,
    output: Path,
    add_dir: Path | None = None,
    trust_project: bool = True,
    hook_trust: bool = False,
    ignore_rules: bool = False,
) -> list[str]:
    args = [
        "codex",
        "exec",
        "--ephemeral",
        "--json",
        "--ignore-user-config",
        "--model",
        MODEL,
        "--sandbox",
        sandbox,
        "-c",
        "approval_policy=\"never\"",
        "-c",
        "sandbox_workspace_write.network_access=false",
    ]
    if trust_project:
        args += ["-c", f"projects.{toml_quote(str(cwd.resolve()))}.trust_level=\"trusted\""]
    if hook_trust:
        args.append("--dangerously-bypass-hook-trust")
    if ignore_rules:
        args.append("--ignore-rules")
    if add_dir is not None:
        args += [
            "-c",
            f"sandbox_workspace_write.writable_roots=[{toml_quote(str(add_dir.resolve()))}]",
        ]
    args += ["--output-schema", str(schema.resolve()), "-o", str(output.resolve())]
    return args


def run_codex(
    *,
    cwd: Path,
    prompt: str,
    schema: Path,
    output: Path,
    sandbox: str,
    add_dir: Path | None = None,
    trust_project: bool = True,
    hook_trust: bool = False,
    ignore_rules: bool = False,
    timeout: int = 600,
) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    output.unlink(missing_ok=True)
    args = common_codex_args(
        cwd=cwd,
        sandbox=sandbox,
        schema=schema,
        output=output,
        add_dir=add_dir,
        trust_project=trust_project,
        hook_trust=hook_trust,
        ignore_rules=ignore_rules,
    )
    args.append(prompt)
    try:
        completed = run(args, cwd=cwd, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {}, {"timeout": True}, "Codex invocation timed out"
    summary = event_summary(completed.stdout)
    if completed.returncode != 0:
        stderr_tail = sanitize_text(completed.stderr[-2500:])
        return {}, summary, f"Codex exited {completed.returncode}: {stderr_tail}"
    if not output.is_file():
        return {}, summary, "Codex did not produce the structured output file"
    try:
        payload = load_json(output)
    except (OSError, json.JSONDecodeError) as exc:
        return {}, summary, f"Codex produced invalid structured output: {exc}"
    if not isinstance(payload, dict):
        return {}, summary, "Codex structured output was not a JSON object"
    return sanitize(payload), summary, None


def write_schemas(directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    planner = {
        "type": "object",
        "properties": {
            "capability_id": {"type": "string"},
            "setup_summary": {"type": "array", "items": {"type": "string"}},
            "trials": {
                "type": "array",
                "minItems": 1,
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "prompt": {"type": "string"},
                        "sandbox": {"type": "string", "enum": ["read-only", "workspace-write"]},
                        "reset_before": {"type": "boolean"},
                    },
                    "required": ["name", "prompt", "sandbox", "reset_before"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["capability_id", "setup_summary", "trials"],
        "additionalProperties": False,
    }
    trial = {
        "type": "object",
        "properties": {
            "capability_id": {"type": "string"},
            "trial": {"type": "string"},
            "outcome": {"type": "string", "enum": ["PASS", "FAIL", "BLOCKED"]},
            "assertions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "status": {"type": "string", "enum": ["PASS", "FAIL", "BLOCKED"]},
                        "evidence": {"type": "string"},
                    },
                    "required": ["name", "status", "evidence"],
                    "additionalProperties": False,
                },
            },
            "observations": {"type": "array", "items": {"type": "string"}},
            "blocker": {"type": ["string", "null"]},
        },
        "required": ["capability_id", "trial", "outcome", "assertions", "observations", "blocker"],
        "additionalProperties": False,
    }
    evaluation = {
        "type": "object",
        "properties": {
            "capability_id": {"type": "string"},
            "result": {"type": "string", "enum": ["REPRODUCED", "FAILED", "BLOCKED"]},
            "expected_met": {"type": "boolean"},
            "observations": {"type": "array", "items": {"type": "string"}},
            "blocker": {"type": ["string", "null"]},
            "summary": {"type": "string"},
        },
        "required": ["capability_id", "result", "expected_met", "observations", "blocker", "summary"],
        "additionalProperties": False,
    }
    paths = {
        "planner": directory / "planner.schema.json",
        "trial": directory / "trial.schema.json",
        "evaluation": directory / "evaluation.schema.json",
    }
    json_dump(paths["planner"], planner)
    json_dump(paths["trial"], trial)
    json_dump(paths["evaluation"], evaluation)
    return paths


def ensure_git_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    if (repo / ".git").exists():
        shutil.rmtree(repo / ".git")
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "PlanAnvil Qualification")
    git(repo, "config", "user.email", "plananvil-qualification@example.invalid")
    git(repo, "config", "commit.gpgsign", "false")
    git(repo, "config", "protocol.file.allow", "always")
    git(repo, "add", "-A")
    git(repo, "commit", "--allow-empty", "-q", "-m", "Initialize qualification fixture")


def commit_fixture_baseline(repo: Path) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "--allow-empty", "-q", "-m", "Prepare capability fixture")
    return git(repo, "rev-parse", "HEAD")


def cleanup_linked_worktrees(repo: Path, worktrees_root: Path) -> None:
    completed = run(["git", "worktree", "list", "--porcelain"], cwd=repo, check=False, timeout=30)
    repo_real = repo.resolve()
    for line in completed.stdout.splitlines():
        if not line.startswith("worktree "):
            continue
        candidate = Path(line[len("worktree "):]).resolve()
        if candidate == repo_real:
            continue
        try:
            candidate.relative_to(worktrees_root.resolve())
        except ValueError:
            continue
        run(["git", "worktree", "remove", "--force", str(candidate)], cwd=repo, check=False, timeout=30)
    run(["git", "worktree", "prune"], cwd=repo, check=False, timeout=30)
    if worktrees_root.exists():
        shutil.rmtree(worktrees_root)
    worktrees_root.mkdir(parents=True, exist_ok=True)


def reset_fixture(repo: Path, baseline: str, worktrees_root: Path) -> None:
    cleanup_linked_worktrees(repo, worktrees_root)
    git(repo, "reset", "--hard", "-q", baseline)
    git(repo, "clean", "-fdx", "-q")


def git_snapshot(repo: Path) -> dict[str, Any]:
    head = git(repo, "rev-parse", "HEAD", check=False) or None
    branch = git(repo, "symbolic-ref", "--short", "-q", "HEAD", check=False) or "DETACHED"
    status = [sanitize_text(line) for line in git(repo, "status", "--porcelain=v1", "--untracked-files=all", check=False).splitlines()]
    refs = git(
        repo,
        "for-each-ref",
        "--format=%(refname)",
        "refs/heads",
        "refs/tags",
        check=False,
    ).splitlines()
    worktree_output = git(repo, "worktree", "list", "--porcelain", check=False)
    worktree_count = sum(1 for line in worktree_output.splitlines() if line.startswith("worktree "))
    index_tree = git(repo, "write-tree", check=False) or None
    commit_count_text = git(repo, "rev-list", "--count", "HEAD", check=False)
    commit_count = int(commit_count_text) if commit_count_text.isdigit() else None
    cached_paths = git(repo, "diff", "--cached", "--name-only", check=False).splitlines()
    return {
        "head": head,
        "branch": branch,
        "status": status,
        "refs": sorted(refs),
        "worktree_count": worktree_count,
        "index_tree": index_tree,
        "commit_count": commit_count,
        "cached_paths": sorted(cached_paths),
    }


def validate_plan(capability_id: str, plan: dict[str, Any]) -> str | None:
    if plan.get("capability_id") != capability_id:
        return f"planner capability_id mismatch: {plan.get('capability_id')!r}"
    trials = plan.get("trials")
    if not isinstance(trials, list) or not trials:
        return "planner returned no trials"
    names: set[str] = set()
    for item in trials:
        if not isinstance(item, dict):
            return "planner returned a non-object trial"
        name = item.get("name")
        prompt = item.get("prompt")
        if not isinstance(name, str) or not name.strip():
            return "planner returned a trial without a name"
        if name in names:
            return f"planner returned duplicate trial name: {name}"
        names.add(name)
        if not isinstance(prompt, str) or not prompt.strip():
            return f"planner returned empty prompt for trial {name}"
    return None


def update_index(index_path: Path, capability_id: str, result: str) -> bool:
    index = load_json(index_path)
    required = False
    for item in index.get("capabilities", []):
        if item.get("id") == capability_id:
            item["result"] = result
            required = bool(item.get("required"))
            break
    else:
        raise QualificationError(f"{capability_id}: missing from capability index")
    json_dump(index_path, index)
    return required


def update_readme(
    path: Path,
    *,
    result: str,
    date: str,
    version: str,
    os_name: str,
    source_commit: str,
    blocker: str | None,
) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^- Current result:.*$", f"- Current result: `{result}`", text)
    text = re.sub(r"(?m)^- Qualification attempt:.*$", f"- Qualification attempt: `{date}`", text)
    text = re.sub(r"(?m)^- Live blocker:.*$", "", text)
    marker = "\n## Live qualification\n"
    if marker in text:
        text = text.split(marker, 1)[0].rstrip() + "\n"
    lines = [
        "",
        "## Live qualification",
        "",
        f"- Date: `{date}`",
        f"- Codex: `{version}`",
        f"- Model: `{MODEL}`",
        f"- OS: `{os_name}`",
        "- Permission mode: `approval=never; sandbox=per-trial; model-tool network disabled`",
        "- Project trust: `trusted via CLI override for disposable fixture repositories`",
        f"- Source commit: `{source_commit}`",
        f"- Result: `{result}`",
    ]
    if blocker:
        lines.append(f"- Blocker: `{sanitize_text(blocker)}`")
    path.write_text(text.rstrip() + "\n" + "\n".join(lines) + "\n", encoding="utf-8")


def rehash_and_validate(root: Path, capability_id: str) -> None:
    run([sys.executable, "tools/rehash_capability.py", capability_id], cwd=root, timeout=60)
    run([sys.executable, "tools/validate_capabilities.py"], cwd=root, timeout=60)


def write_evidence(
    *,
    root: Path,
    capability_id: str,
    result: str,
    expected_met: bool,
    observations: list[str],
    blocker: str | None,
    summary: str,
    trials: list[dict[str, Any]],
    fixture_commit: str | None,
    version: str,
    os_name: str,
    source_commit: str,
    date: str,
) -> bool:
    directory = root / "capabilities" / capability_id
    safe_observations = sanitize(observations)
    safe_trials = sanitize(trials)
    safe_blocker = sanitize_text(blocker) if blocker else None
    actual: dict[str, Any] = {
        "schema_version": "1.0",
        "capability_id": capability_id,
        "result": result,
        "environment": {
            "codex_version": version,
            "model": MODEL,
            "os": os_name,
            "permission_mode": "approval=never; sandbox=per-trial; model-tool network disabled",
            "project_trust": "trusted via CLI override for disposable fixture repositories",
            "source_commit": source_commit,
            "fixture_commit": fixture_commit or "unavailable",
        },
        "observations": safe_observations,
        "trials": safe_trials,
    }
    if result == "BLOCKED":
        actual["blocker"] = safe_blocker or "Live capability could not be exercised completely."
    elif result == "FAILED":
        actual["failure"] = safe_blocker or sanitize_text(summary)
    evaluation = {
        "schema_version": "1.0",
        "capability_id": capability_id,
        "result": result,
        "expected_met": bool(expected_met),
        "summary": sanitize_text(summary),
    }
    if result == "BLOCKED":
        evaluation["blocker"] = actual["blocker"]
    elif result == "FAILED":
        evaluation["failure"] = actual.get("failure")
    json_dump(directory / "actual.sanitized.json", actual)
    json_dump(directory / "evaluation.json", evaluation)
    required = update_index(root / "capabilities" / "index.json", capability_id, result)
    update_readme(
        directory / "README.md",
        result=result,
        date=date,
        version=version,
        os_name=os_name,
        source_commit=source_commit,
        blocker=safe_blocker if result != "REPRODUCED" else None,
    )
    rehash_and_validate(root, capability_id)
    return required


def local_commit(root: Path, capability_id: str) -> None:
    git(root, "add", "capabilities")
    completed = run(["git", "diff", "--cached", "--quiet"], cwd=root, check=False, timeout=30)
    if completed.returncode == 0:
        return
    run(
        ["git", "commit", "-q", "-m", f"Record live evidence for {capability_id}"],
        cwd=root,
        timeout=60,
    )


def copy_spec(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


def prepare_evaluator_repo(
    directory: Path,
    *,
    expected: Path,
    trial_payloads: list[dict[str, Any]],
) -> Path:
    if directory.exists():
        shutil.rmtree(directory)
    input_dir = directory / "input"
    input_dir.mkdir(parents=True)
    shutil.copy2(expected, input_dir / "expected.json")
    json_dump(input_dir / "trials.sanitized.json", sanitize(trial_payloads))
    ensure_git_repo(directory)
    git(directory, "add", "-A")
    git(directory, "commit", "--allow-empty", "-q", "-m", "Prepare evaluation input")
    return directory


def planner_prompt(capability_id: str) -> str:
    return f"""You are preparing live Codex capability test {capability_id} in a disposable Git repository.

The immutable test specification is available at ../spec. Read:
- ../spec/README.md
- ../spec/fixture/
- ../spec/config/
- ../spec/prompt.txt
- ../spec/run-command.txt
- ../spec/expected.json

First, instantiate the fixture and configuration described by that package inside the CURRENT repository. Do not modify ../spec. Do not create or edit actual.sanitized.json, evaluation.json, hashes.json, or any source repository outside the current disposable fixture.

Then return the structured trial plan. Each trial must be a fresh, independent `codex exec --ephemeral` invocation performed by the outer harness. Use separate trials when the specification compares different prompts or modes (for example implicit vs explicit activation). Do not ask a trial to invoke Codex recursively. Use at most 8 trials. `reset_before` should be false only when the specification genuinely requires state produced by an earlier trial. Sandbox must be the least privilege needed: read-only or workspace-write.

The protected PlanAnvil source snapshot under test is readable at ../../.. . You may read it and copy required PlanAnvil-owned fixture files into the CURRENT disposable repository, but you must not modify that source snapshot.

Ground the plan only in ../spec plus that protected source snapshot. Do not mark the capability reproduced; the outer evaluator will decide that from observed trial evidence."""


def trial_prompt(capability_id: str, trial: dict[str, Any]) -> str:
    return f"""Execute one live PlanAnvil Codex capability trial.

Capability: {capability_id}
Trial: {trial['name']}

The immutable expected behavior is readable at ../spec/expected.json. The disposable fixture repository has already been prepared from ../spec/fixture and ../spec/config. The protected PlanAnvil source snapshot is readable at ../../.. if the trial needs to inspect PlanAnvil-owned code; it is read-only to this sandbox.

Trial instruction:
{trial['prompt']}

Rules:
- Exercise the requested runtime behavior; do not merely describe documentation.
- Do not invoke `codex` recursively.
- Do not access the network from model-generated commands.
- Do not modify ../spec.
- Keep all filesystem/Git mutations inside this disposable fixture repository or the provided ../worktrees auxiliary directory.
- Never read, print, or copy credentials, auth files, environment secrets, usernames, home paths, session identifiers, or unrelated files.
- Return only minimal structural observations needed to evaluate ../spec/expected.json.
- PASS means this trial actually demonstrated its expected behavior; FAIL means it demonstrated contrary behavior; BLOCKED means the runtime could not exercise it.
"""


def evaluator_prompt(capability_id: str) -> str:
    return f"""Evaluate live capability {capability_id} using only the sanitized evidence in input/.

Read input/expected.json and input/trials.sanitized.json. Do not use documentation or assumptions to fill evidence gaps.

Decision rules:
- REPRODUCED only if the trial evidence actually demonstrates every material assertion required by expected.json.
- FAILED if a completed trial demonstrates behavior contrary to an expected assertion.
- BLOCKED if required behavior was not actually exercised, evidence is incomplete, or the runtime prevented a necessary test.
- For REPRODUCED set expected_met=true and blocker=null.
- Do not include absolute paths, session/thread identifiers, credentials, URLs containing secrets, or private user data.
Return concise structural observations that make the decision auditable."""


def capability_runtime(
    *,
    root: Path,
    runtime_root: Path,
    capability_id: str,
    schemas: dict[str, Path],
    version: str,
    os_name: str,
    source_commit: str,
    date: str,
) -> tuple[str, bool]:
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
    copy_spec(cap_dir, spec_dir)
    spec_hashes = sha256_tree(spec_dir)
    ensure_git_repo(repo)

    planner_output = results_dir / "planner.json"
    plan, planner_events, planner_error = run_codex(
        cwd=repo,
        prompt=planner_prompt(capability_id),
        schema=schemas["planner"],
        output=planner_output,
        sandbox="workspace-write",
        trust_project=True,
        hook_trust=False,
        ignore_rules=False,
        timeout=600,
    )
    trial_payloads: list[dict[str, Any]] = []
    if planner_error:
        result = "BLOCKED"
        expected_met = False
        observations = [f"Planner invocation could not prepare the live fixture: {planner_error}"]
        blocker = planner_error
        summary = f"{capability_id} blocked during fixture preparation."
        fixture_commit = None
    else:
        plan_error = validate_plan(capability_id, plan)
        if sha256_tree(spec_dir) != spec_hashes:
            plan_error = "planner modified the immutable capability specification"
        if plan_error:
            result = "BLOCKED"
            expected_met = False
            observations = [plan_error]
            blocker = plan_error
            summary = f"{capability_id} blocked because the generated trial plan was invalid."
            fixture_commit = None
        else:
            fixture_commit = commit_fixture_baseline(repo)
            baseline = fixture_commit
            for position, trial in enumerate(plan["trials"], start=1):
                if trial.get("reset_before", True):
                    reset_fixture(repo, baseline, worktrees)
                before = git_snapshot(repo)
                trial_output = results_dir / f"trial-{position:02d}.json"
                payload, events, error = run_codex(
                    cwd=repo,
                    prompt=trial_prompt(capability_id, trial),
                    schema=schemas["trial"],
                    output=trial_output,
                    sandbox=trial["sandbox"],
                    add_dir=worktrees if trial["sandbox"] == "workspace-write" else None,
                    trust_project=True,
                    hook_trust=True,
                    ignore_rules=False,
                    timeout=600,
                )
                after = git_snapshot(repo)
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
                trial_payloads.append(sanitize(payload))
                if sha256_tree(spec_dir) != spec_hashes:
                    trial_payloads[-1]["outcome"] = "BLOCKED"
                    trial_payloads[-1]["blocker"] = "trial modified the immutable capability specification"
                    break

            prepare_evaluator_repo(
                evaluator_dir,
                expected=cap_dir / "expected.json",
                trial_payloads=trial_payloads,
            )
            eval_output = results_dir / "evaluation.json"
            evaluation, evaluation_events, evaluation_error = run_codex(
                cwd=evaluator_dir,
                prompt=evaluator_prompt(capability_id),
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
                trial_payloads.append(
                    {
                        "evaluator_event_summary": evaluation_events,
                    }
                )

    required = write_evidence(
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
    local_commit(root, capability_id)
    shutil.rmtree(cap_runtime, ignore_errors=True)
    return result, required


def stage_artifact(root: Path, output: Path, summary: dict[str, Any]) -> None:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    capabilities_out = output / "capabilities"
    capabilities_out.mkdir()
    shutil.copy2(root / "capabilities" / "README.md", capabilities_out / "README.md")
    shutil.copy2(root / "capabilities" / "index.json", capabilities_out / "index.json")
    for capability_id in CAPABILITY_IDS:
        shutil.copytree(root / "capabilities" / capability_id, capabilities_out / capability_id)
    json_dump(output / "qualification-summary.json", sanitize(summary))


def finalize_index(root: Path, *, date: str, source_commit: str, run_id: str, results: dict[str, str]) -> None:
    path = root / "capabilities" / "index.json"
    index = load_json(path)
    required_missing = [
        item["id"]
        for item in index.get("capabilities", [])
        if item.get("required") and results.get(item["id"]) != "REPRODUCED"
    ]
    index["generated_at"] = date
    index["evidence_package_state"] = (
        "LIVE_QUALIFIED" if not required_missing else "LIVE_QUALIFICATION_PARTIAL"
    )
    index["qualification_attempt"] = {
        "date": date,
        "source_commit": source_commit,
        "github_actions_run": run_id,
        "live_codex_result": "PASS" if not required_missing else "PARTIAL",
        "required_not_reproduced": required_missing,
    }
    json_dump(path, index)
    run([sys.executable, "tools/rehash_capability.py", "--all"], cwd=root, timeout=120)
    run([sys.executable, "tools/validate_capabilities.py"], cwd=root, timeout=120)
    git(root, "add", "capabilities")
    completed = run(["git", "diff", "--cached", "--quiet"], cwd=root, check=False, timeout=30)
    if completed.returncode != 0:
        run(["git", "commit", "-q", "-m", "Finalize live Codex qualification index"], cwd=root, timeout=60)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run PlanAnvil C01-C16 live Codex qualification")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not (root / ".git").exists():
        raise QualificationError(f"qualification root is not a Git repository: {root}")
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_commit):
        raise QualificationError("--source-commit must be a full Git SHA")
    if git(root, "rev-parse", "HEAD") != args.source_commit:
        raise QualificationError("qualification repository HEAD does not match --source-commit")

    version = codex_version()
    os_name = os_label()
    date = dt.date.today().isoformat()

    # Materialized capability packages must already be present and valid.
    run([sys.executable, "tools/validate_capabilities.py"], cwd=root, timeout=120)
    git(root, "config", "user.name", "PlanAnvil Qualification")
    git(root, "config", "user.email", "plananvil-qualification@example.invalid")
    git(root, "config", "commit.gpgsign", "false")
    git(root, "config", "protocol.file.allow", "always")
    git(root, "add", "capabilities")
    run(
        ["git", "commit", "--allow-empty", "-q", "-m", "Materialize capability qualification templates"],
        cwd=root,
        timeout=60,
    )

    runtime_root = root / ".qualification-runtime"
    if runtime_root.exists():
        shutil.rmtree(runtime_root)
    runtime_root.mkdir()
    exclude = root / ".git" / "info" / "exclude"
    with exclude.open("a", encoding="utf-8") as handle:
        handle.write("\n.qualification-runtime/\n")
    schemas = write_schemas(runtime_root / "schemas")

    results: dict[str, str] = {}
    required_flags: dict[str, bool] = {}
    try:
        for capability_id in CAPABILITY_IDS:
            print(f"=== {capability_id}: live qualification ===", flush=True)
            try:
                result, required = capability_runtime(
                    root=root,
                    runtime_root=runtime_root,
                    capability_id=capability_id,
                    schemas=schemas,
                    version=version,
                    os_name=os_name,
                    source_commit=args.source_commit,
                    date=date,
                )
            except Exception as exc:  # Continue sequentially; leave an auditable blocker.
                blocker = sanitize_text(f"{type(exc).__name__}: {exc}")
                print(f"{capability_id}: controller error: {blocker}", file=sys.stderr, flush=True)
                required = bool(
                    next(
                        (
                            item.get("required")
                            for item in load_json(root / "capabilities" / "index.json")["capabilities"]
                            if item.get("id") == capability_id
                        ),
                        False,
                    )
                )
                write_evidence(
                    root=root,
                    capability_id=capability_id,
                    result="BLOCKED",
                    expected_met=False,
                    observations=[f"Qualification controller blocked before completing {capability_id}."],
                    blocker=blocker,
                    summary=f"{capability_id} blocked by qualification controller error.",
                    trials=[],
                    fixture_commit=None,
                    version=version,
                    os_name=os_name,
                    source_commit=args.source_commit,
                    date=date,
                )
                local_commit(root, capability_id)
                result = "BLOCKED"
            results[capability_id] = result
            required_flags[capability_id] = required
            print(f"{capability_id}: {result}", flush=True)

        finalize_index(
            root,
            date=date,
            source_commit=args.source_commit,
            run_id=args.run_id,
            results=results,
        )
        required_missing = [
            capability_id
            for capability_id in CAPABILITY_IDS
            if required_flags.get(capability_id) and results.get(capability_id) != "REPRODUCED"
        ]
        summary = {
            "schema_version": "1.0",
            "date": date,
            "source_commit": args.source_commit,
            "github_actions_run": args.run_id,
            "codex_version": version,
            "model": MODEL,
            "os": os_name,
            "results": results,
            "required_not_reproduced": required_missing,
            "release_gate_passed": not required_missing,
        }
        stage_artifact(root, args.output.resolve(), summary)
        print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
        return 0 if not required_missing else 2
    finally:
        shutil.rmtree(runtime_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
