from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Iterator

import live_codex_qualification_harness as v1
import live_codex_qualification_harness_v2 as v2
import live_codex_qualification_harness_v4 as v4
import live_codex_qualification_harness_v5 as v5

base = v5.base
TARGET_CAPABILITIES = {"C03", "C06", "C08", "C09", "C13", "C16"}
HOOK_LOG_ENV = "PLANANVIL_QUAL_HOOK_LOG"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _runtime_paths(**kwargs: Any):
    return v2._runtime_paths(**kwargs)


def _write_result(**kwargs: Any):
    return v4._write_result(**kwargs)


def _sidecar(cap_runtime: Path, name: str) -> Path:
    path = cap_runtime / "hook-telemetry" / f"{name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _read_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out


@contextlib.contextmanager
def _hook_env(path: Path) -> Iterator[None]:
    path.unlink(missing_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    previous_log = os.environ.get(HOOK_LOG_ENV)
    previous_tmp = os.environ.get("TMPDIR")
    os.environ[HOOK_LOG_ENV] = str(path.resolve())
    os.environ["TMPDIR"] = str(path.parent.resolve())
    try:
        yield
    finally:
        if previous_log is None:
            os.environ.pop(HOOK_LOG_ENV, None)
        else:
            os.environ[HOOK_LOG_ENV] = previous_log
        if previous_tmp is None:
            os.environ.pop("TMPDIR", None)
        else:
            os.environ["TMPDIR"] = previous_tmp


def _fail_open_proxy_source() -> str:
    return r'''from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path

event_name, script_name = sys.argv[1], sys.argv[2]
raw = sys.stdin.read()
try:
    event = json.loads(raw) if raw.strip() else {}
except json.JSONDecodeError:
    event = {}
root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
completed = subprocess.run(
    [sys.executable, str(root / ".codex" / "hooks" / script_name)],
    input=raw, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
)
record = {"event": event_name, "returncode": completed.returncode}
if isinstance(event, dict) and isinstance(event.get("tool_name"), str):
    record["tool_name"] = event["tool_name"]
try:
    parsed = json.loads(completed.stdout) if completed.stdout.strip() else {}
except json.JSONDecodeError:
    parsed = {}
if isinstance(parsed, dict):
    if "continue" in parsed:
        record["continue"] = parsed.get("continue")
    reason = parsed.get("stopReason")
    if isinstance(reason, str):
        lowered = reason.lower()
        record["stop_reason_mentions_checkpoint"] = "checkpoint" in lowered
        record["stop_reason_mentions_recovery"] = "recovery" in lowered or "canonical state" in lowered
    output = parsed.get("hookSpecificOutput")
    if isinstance(output, dict):
        record["additional_context"] = bool(output.get("additionalContext"))
        if isinstance(output.get("permissionDecision"), str):
            record["permission_decision"] = output["permissionDecision"]
try:
    log_value = os.environ.get("PLANANVIL_QUAL_HOOK_LOG")
    if log_value:
        log = Path(log_value)
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
except Exception:
    pass
# Recorder failure is never allowed to change the hook result.
sys.stdout.write(completed.stdout)
sys.stderr.write(completed.stderr)
raise SystemExit(completed.returncode)
'''


def _compact_prompt(capability_id: str, names: list[str]) -> str:
    # Duplicate every large read so a low body-after-prefix threshold must be
    # crossed before the final status commands, while preserving one model turn.
    expanded = [name for name in names for _ in range(2)]
    commands = "\n".join(
        f"- run `cat qualification-payload/{name}` in a separate shell-tool call"
        for name in expanded
    )
    return f"""Exercise genuine Codex automatic compaction for {capability_id}.
Do not invoke hook scripts directly, simulate hook events, or inspect qualification telemetry.
Execute these reads in order, continuing normally after any automatic compaction:
{commands}
After the reads, run `git status --porcelain=v1 --untracked-files=all` and `git rev-parse HEAD`.
Return capability_id {capability_id} with only minimal structural observations.
"""


@contextlib.contextmanager
def _patched_v4(cap_runtime: Path, capability_id: str) -> Iterator[None]:
    old_proxy = v4._hook_proxy_source
    old_hook_log = v4._hook_log
    old_run = v4._run_codex_probe
    old_prompt = v4._compact_probe_prompt
    old_c08 = v4.C08_COMPACT_LIMIT
    old_c09 = v4.C09_COMPACT_LIMIT
    log = _sidecar(cap_runtime, capability_id.lower())

    def hook_log(_repo: Path) -> Path:
        return log

    def run_probe(**kwargs: Any):
        with _hook_env(log):
            return old_run(**kwargs)

    v4._hook_proxy_source = _fail_open_proxy_source
    v4._hook_log = hook_log
    v4._run_codex_probe = run_probe
    v4._compact_probe_prompt = _compact_prompt
    v4.C08_COMPACT_LIMIT = 40
    v4.C09_COMPACT_LIMIT = 200
    try:
        yield
    finally:
        v4._hook_proxy_source = old_proxy
        v4._hook_log = old_hook_log
        v4._run_codex_probe = old_run
        v4._compact_probe_prompt = old_prompt
        v4.C08_COMPACT_LIMIT = old_c08
        v4.C09_COMPACT_LIMIT = old_c09


def run_c08(**kwargs: Any):
    cap_runtime = Path(kwargs["runtime_root"]) / "C08"
    with _patched_v4(cap_runtime, "C08"):
        return v4._c08_runtime(**kwargs)


def run_c09(**kwargs: Any):
    cap_runtime = Path(kwargs["runtime_root"]) / "C09"
    with _patched_v4(cap_runtime, "C09"):
        return v4._c09_runtime(**kwargs)


@contextlib.contextmanager
def _patched_v5_c13(cap_runtime: Path) -> Iterator[None]:
    old_proxy = v5._c13_hook_proxy_source
    old_hook_log = v5._hook_log
    old_run = v5._run_c13_codex

    def hook_log(repo: Path) -> Path:
        return _sidecar(cap_runtime, f"c13-{repo.name}")

    def run_c13(**kwargs: Any):
        log = hook_log(Path(kwargs["repo"]))
        with _hook_env(log):
            return old_run(**kwargs)

    v5._c13_hook_proxy_source = _fail_open_proxy_source
    v5._hook_log = hook_log
    v5._run_c13_codex = run_c13
    try:
        yield
    finally:
        v5._c13_hook_proxy_source = old_proxy
        v5._hook_log = old_hook_log
        v5._run_c13_codex = old_run


def run_c13(current_runtime: Callable[..., tuple[str, bool]], **kwargs: Any):
    cap_runtime = Path(kwargs["runtime_root"]) / "C13"
    with _patched_v5_c13(cap_runtime):
        return current_runtime(**kwargs)


# C03 -----------------------------------------------------------------------

def run_c03(
    *, root: Path, runtime_root: Path, schemas: dict[str, Path], version: str,
    os_name: str, source_commit: str, date: str,
) -> tuple[str, bool]:
    cid = "C03"
    _cap, cap_runtime, _spec, driver, worktrees, results, _eval = _runtime_paths(
        root=root, runtime_root=runtime_root, capability_id=cid
    )
    with v2._python_bytecode_disabled():
        base.ensure_git_repo(driver)
        _write(driver / "README.md", "C03 command driver.\n")
        base.commit_fixture_baseline(driver)
        source = worktrees / "source"
        base.ensure_git_repo(source)
        branch = base.git(source, "branch", "--show-current", check=False)
        if branch and branch != "main":
            base.git(source, "branch", "-m", "main")
        v1._install_plananvil_release(root, source)
        _write(source / "README.md", "C03 topology fixture.\n")
        fixture_commit = base.commit_fixture_baseline(source)
        before = base.git_snapshot(source)
        planning = worktrees / "planning"
        start = base.run([
            sys.executable, ".agents/skills/plan-anvil/scripts/plan_anvil.py", "start",
            "--source", ".", "--destination", str(planning),
            "--goal", "Qualify PlanAnvil flat direct-child topology",
            "--codex-version", version, "--model", base.MODEL,
            "--permission-mode", "approval=never; sandbox=workspace-write",
            "--project-trust", "TRUSTED", "--hook-mode", "HOOKS_TRUSTED",
        ], cwd=source, check=False, timeout=240)
        try:
            start_payload = v1._parse_json_stdout(start, "PlanAnvil start")
        except Exception:
            start_payload = {}
        bootstrap_ok = start.returncode == 0 and bool(start_payload.get("planning_worktree"))
        after_bootstrap = base.git_snapshot(source)
        source_core_unchanged = all(
            before.get(key) == after_bootstrap.get(key)
            for key in ("head", "branch", "status", "index_tree", "cached_paths")
        )
        config = (source / ".codex" / "config.toml").read_text(encoding="utf-8")
        config_ok = (
            "enabled = true" in config
            and "max_concurrent_threads_per_session" in config
            and "max_depth" not in config
        )
        contract = root / ".agents" / "skills" / "plan-anvil" / "references" / "execution-contract.md"
        contract_text = contract.read_text(encoding="utf-8")
        contract_ok = (
            re.search(r"flat\s+direct[- ]child\s+topology", contract_text, re.I) is not None
            and "agents.max_depth" not in contract_text
            and "max_depth" not in contract_text
        )
        golden = root / "examples" / "small-change" / "run" / "PLAN.md"
        code = r'''import json, sys
from pathlib import Path
sys.path.insert(0, str(Path('.agents/skills/plan-anvil/scripts').resolve()))
from execution_contract import execution_contract_findings
print(json.dumps(execution_contract_findings(Path(sys.argv[1]).read_text(encoding='utf-8')), sort_keys=True))
'''
        check = base.run([sys.executable, "-B", "-c", code, str(golden.resolve())], cwd=source, check=False, timeout=120)
        try:
            findings = json.loads(check.stdout) if check.returncode == 0 else []
        except json.JSONDecodeError:
            findings = []
        validator_ok = check.returncode == 0 and not any(
            isinstance(item, dict) and item.get("kind") == "execution-contract-topology-missing"
            for item in findings
        )
        prompt = (
            "Use only shell tools to verify the explicit auxiliary C03 source is reachable and clean. "
            "Run exactly `cd ../worktrees/source && git status --porcelain=v1 && git rev-parse HEAD`. "
            "Do not modify files or start subagents. Return capability_id C03, trial explicit_plananvil_topology, "
            "outcome PASS when both commands succeed and status is clean."
        )
        payload, events, error = v4._run_codex_probe(
            cwd=driver, prompt=prompt, schemas=schemas, results_dir=results,
            position=1, sandbox="workspace-write", add_dir=worktrees, timeout=600,
        )
        live_ok = error is None and payload.get("outcome") == "PASS"
    assertions = {
        "bootstrap_git_probe_completed": bootstrap_ok,
        "source_branch_head_index_files_preserved": source_core_unchanged,
        "agents_config_current_and_no_max_depth": config_ok,
        "plananvil_contract_flat_direct_child_and_no_max_depth": contract_ok,
        "current_golden_plan_passes_topology_validator": validator_ok,
        "live_codex_auxiliary_source_probe": live_ok,
    }
    if not bootstrap_ok or not live_ok:
        result, met = "BLOCKED", False
        blocker = error or "C03 auxiliary PlanAnvil bootstrap/live probe did not complete."
    elif not all(assertions.values()):
        result, met = "FAILED", False
        blocker = "Current PlanAnvil topology/configuration contradicted the C03 contract."
    else:
        result, met, blocker = "REPRODUCED", True, None
    trial = {
        "capability_id": cid, "trial": "explicit_plananvil_topology", "trial_name": "explicit_plananvil_topology",
        "outcome": "PASS" if met else ("BLOCKED" if result == "BLOCKED" else "FAIL"),
        "assertions": [
            {"name": key, "status": "PASS" if value else ("BLOCKED" if result == "BLOCKED" else "FAIL"), "evidence": str(value).lower()}
            for key, value in assertions.items()
        ],
        "observations": [f"{key}={str(value).lower()}" for key, value in assertions.items()],
        "blocker": blocker, "event_summary": events, "model_payload": payload,
        "contract_sha256": _sha256(contract), "golden_plan_sha256": _sha256(golden),
    }
    return _write_result(
        root=root, cap_runtime=cap_runtime, capability_id=cid, result=result,
        expected_met=met, observations=trial["observations"], blocker=blocker,
        summary=("C03 reproduced with explicit writable Git bootstrap and deterministic flat direct-child contract validation." if met else "C03 did not fully reproduce after regression-audited setup."),
        trials=[trial], fixture_commit=fixture_commit, version=version, os_name=os_name,
        source_commit=source_commit, date=date,
    )


# C06 -----------------------------------------------------------------------

def _minimal_hook_source() -> str:
    return r'''from __future__ import annotations
import json, os, sys
from pathlib import Path
try:
    event = json.load(sys.stdin)
except Exception:
    event = {}
try:
    log = Path(os.environ["PLANANVIL_QUAL_HOOK_LOG"])
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event": "PreToolUse", "tool_name": event.get("tool_name")}, sort_keys=True) + "\n")
except Exception:
    pass
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}, sort_keys=True))
'''


def _patch_prompt(trial: str, target: str, marker: str) -> str:
    return (
        f"Use the direct apply_patch tool exactly once to add `{target}` containing only `{marker}`. "
        "Do not create it with shell commands and do not execute hook scripts manually. "
        f"Return capability_id C06, trial {trial}, outcome PASS after the direct patch completes."
    )


def run_c06(
    *, root: Path, runtime_root: Path, schemas: dict[str, Path], version: str,
    os_name: str, source_commit: str, date: str,
) -> tuple[str, bool]:
    cid = "C06"
    _cap, cap_runtime, _spec, repo, _worktrees, results, _eval = _runtime_paths(
        root=root, runtime_root=runtime_root, capability_id=cid
    )
    with v2._python_bytecode_disabled(), _patched_v4(cap_runtime, cid):
        base.ensure_git_repo(repo)
        v1._install_plananvil_release(root, repo)
        v4._instrument_hooks(repo, event_to_script={"PreToolUse": "plan-anvil-guard.py"})
        _write(repo / "README.md", "C06 integrated fixture.\n")
        fixture_commit = base.commit_fixture_baseline(repo)
        log = v4._hook_log(repo)
        before = base.git_snapshot(repo)
        payload_i, events_i, error_i = v4._run_codex_probe(
            cwd=repo, prompt=_patch_prompt("supported_apply_patch", ".pursue/c06-supported.txt", "C06_SUPPORTED"),
            schemas=schemas, results_dir=results, position=1, sandbox="workspace-write", timeout=600,
        )
        after = base.git_snapshot(repo)
        records_i = _read_records(log)
        apply_i = [r for r in records_i if r.get("event") == "PreToolUse" and r.get("tool_name") == "apply_patch"]
        integrated_mutation = (repo / ".pursue" / "c06-supported.txt").is_file()
        count_before = len(records_i)
        outer_before = base.git_snapshot(repo)
        with (repo / "README.md").open("a", encoding="utf-8") as handle:
            handle.write("C06_OUTSIDE_HOOK_LIFECYCLE\n")
        outer_after = base.git_snapshot(repo)
        postcondition = any(
            isinstance(line, str) and line.endswith("README.md")
            for line in (outer_after.get("status") or [])
        )
        no_hook = len(_read_records(log)) == count_before

    minimal = cap_runtime / "minimal-repro"
    base.ensure_git_repo(minimal)
    _write(minimal / ".codex" / "hooks" / "minimal-pretooluse.py", _minimal_hook_source())
    _write(minimal / ".codex" / "hooks.json", json.dumps({
        "hooks": {"PreToolUse": [{"matcher": "^apply_patch$", "hooks": [{
            "type": "command",
            "command": 'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/minimal-pretooluse.py"',
            "timeout": 30,
        }]}]}
    }, indent=2, sort_keys=True) + "\n")
    _write(minimal / "README.md", "C06 minimal runtime hook repro.\n")
    base.commit_fixture_baseline(minimal)
    minimal_log = _sidecar(cap_runtime, "c06-minimal")
    minimal_log.unlink(missing_ok=True)
    with _hook_env(minimal_log):
        payload_m, events_m, error_m = v4._run_codex_probe(
            cwd=minimal, prompt=_patch_prompt("minimal_apply_patch_pretooluse", "c06-minimal.txt", "C06_MINIMAL"),
            schemas=schemas, results_dir=results, position=2, sandbox="workspace-write", timeout=600,
        )
    records_m = _read_records(minimal_log)
    apply_m = [r for r in records_m if r.get("event") == "PreToolUse" and r.get("tool_name") == "apply_patch"]
    minimal_mutation = (minimal / "c06-minimal.txt").is_file()

    if error_i or error_m or not integrated_mutation or not minimal_mutation:
        result, met = "BLOCKED", False
        blocker = error_i or error_m or "A direct apply_patch fixture mutation did not complete."
    elif not apply_m:
        result, met = "FAILED", False
        blocker = "Direct apply_patch completed but the isolated current-runtime PreToolUse hook did not fire."
    elif not apply_i:
        result, met = "BLOCKED", False
        blocker = "The isolated PreToolUse hook fired, but the installed PlanAnvil PreToolUse hook did not."
    elif not (postcondition and no_hook):
        result, met = "FAILED", False
        blocker = "Mandatory postcondition detection failed for the intentionally unhooked mutation."
    else:
        result, met, blocker = "REPRODUCED", True, None
    trials = [
        {"capability_id": cid, "trial": "supported_apply_patch", "trial_name": "supported_apply_patch", "outcome": "PASS" if apply_i and integrated_mutation else ("BLOCKED" if error_i else "FAIL"), "assertions": [{"name": "plananvil_apply_patch_pretooluse", "status": "PASS" if apply_i else ("BLOCKED" if error_i else "FAIL"), "evidence": f"events={len(apply_i)}; mutation={str(integrated_mutation).lower()}"}], "observations": [f"apply_patch_pretooluse_events={len(apply_i)}", f"supported_mutation={str(integrated_mutation).lower()}"], "blocker": error_i, "event_summary": events_i, "git_before": before, "git_after": after, "model_payload": payload_i},
        {"capability_id": cid, "trial": "minimal_apply_patch_pretooluse", "trial_name": "minimal_apply_patch_pretooluse", "outcome": "PASS" if apply_m and minimal_mutation else ("BLOCKED" if error_m else "FAIL"), "assertions": [{"name": "isolated_apply_patch_pretooluse", "status": "PASS" if apply_m else ("BLOCKED" if error_m else "FAIL"), "evidence": f"events={len(apply_m)}; mutation={str(minimal_mutation).lower()}"}], "observations": [f"minimal_apply_patch_pretooluse_events={len(apply_m)}", f"minimal_mutation={str(minimal_mutation).lower()}"], "blocker": error_m, "event_summary": events_m, "model_payload": payload_m},
        {"capability_id": cid, "trial": "outer_non_intercepted_postcondition", "trial_name": "outer_non_intercepted_postcondition", "outcome": "PASS" if postcondition and no_hook else "FAIL", "assertions": [{"name": "postcondition_detection", "status": "PASS" if postcondition and no_hook else "FAIL", "evidence": f"detected={str(postcondition).lower()}; hook_count_unchanged={str(no_hook).lower()}"}], "observations": [f"git_postcondition_detected={str(postcondition).lower()}", f"hook_record_count_unchanged={str(no_hook).lower()}"], "blocker": None, "git_before": outer_before, "git_after": outer_after},
    ]
    return _write_result(
        root=root, cap_runtime=cap_runtime, capability_id=cid, result=result,
        expected_met=met, observations=[f"plananvil_events={len(apply_i)}", f"minimal_events={len(apply_m)}", f"postcondition={str(postcondition).lower()}"],
        blocker=blocker,
        summary=("C06 reproduced with integrated and isolated PreToolUse plus mandatory postconditions." if met else "C06 did not fully reproduce after the isolated current-runtime comparison."),
        trials=trials, fixture_commit=fixture_commit, version=version, os_name=os_name,
        source_commit=source_commit, date=date,
    )


# C16 -----------------------------------------------------------------------

def _normalize_main(source: Path) -> None:
    branch = base.git(source, "branch", "--show-current", check=False)
    if not branch:
        base.git(source, "switch", "-c", "main")
    elif branch != "main":
        base.git(source, "branch", "-m", "main")


def _prepare_c16(root: Path, source: Path) -> str:
    _write(source / "source.txt", "C16 source sentinel.\n")
    base.ensure_git_repo(source)
    _normalize_main(source)
    v1._install_plananvil_release(root, source)
    base.git(source, "add", "-A")
    base.git(source, "commit", "--allow-empty", "-q", "-m", "Install PlanAnvil C16 fixture")
    return base.git(source, "rev-parse", "HEAD")


def _clear_signing(source: Path) -> None:
    base.git(source, "config", "commit.gpgsign", "false")
    for key in ("gpg.program", "user.signingkey"):
        base.git(source, "config", "--unset-all", key, check=False)


def _signing_failure(source: Path, fake: Path) -> None:
    _write(fake, "#!/bin/sh\necho 'gpg: signing failed: C16 fixture signing failure' >&2\nexit 1\n")
    fake.chmod(0o755)
    base.git(source, "config", "commit.gpgsign", "true")
    base.git(source, "config", "gpg.format", "openpgp")
    base.git(source, "config", "user.signingkey", "C16-FIXTURE-KEY")
    base.git(source, "config", "gpg.program", str(fake.resolve()))


def _hook_failure(source: Path) -> Path:
    hook = source / ".git" / "hooks" / "pre-commit"
    _write(hook, "#!/bin/sh\necho 'pre-commit hook failed: C16 fixture hook rejection' >&2\nexit 1\n")
    hook.chmod(0o755)
    return hook


def _outer_probe(source: Path, run_id: str, probes: Path) -> tuple[dict[str, Any], str | None]:
    completed = base.run([
        sys.executable, "-B", ".agents/skills/plan-anvil/scripts/test_git_capabilities.py",
        "--source", ".", "--run-id", run_id, "--temp-parent", str(probes),
    ], cwd=source, check=False, timeout=240)
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {}, base.sanitize_text((completed.stderr or completed.stdout)[-1500:])
    return (value if isinstance(value, dict) else {}), None


def _diag(payload: dict[str, Any], needles: tuple[str, ...]) -> bool:
    return any(
        any(needle in str(step.get("detail") or "").lower() for needle in needles)
        for step in payload.get("steps", []) if isinstance(step, dict)
    )


def _c16_prompt(run_id: str, expected: str) -> str:
    return (
        "Run the real PlanAnvil reversible Git capability probe against `../worktrees/source`: "
        f"`cd ../worktrees/source && PYTHONDONTWRITEBYTECODE=1 python .agents/skills/plan-anvil/scripts/test_git_capabilities.py --source . --run-id {run_id} --temp-parent ../probes`. "
        f"Return PASS only when result is {expected}, source_snapshot_changed and cleanup_errors are empty, and no probe artifacts remain."
    )


def run_c16(
    *, root: Path, runtime_root: Path, schemas: dict[str, Path], version: str,
    os_name: str, source_commit: str, date: str,
) -> tuple[str, bool]:
    cid = "C16"
    _cap, cap_runtime, _spec, driver, worktrees, results, _eval = _runtime_paths(
        root=root, runtime_root=runtime_root, capability_id=cid
    )
    with v2._python_bytecode_disabled():
        base.ensure_git_repo(driver)
        _write(driver / "README.md", "C16 command driver.\n")
        base.commit_fixture_baseline(driver)
        source = worktrees / "source"
        fixture_commit = _prepare_c16(root, source)
        probes = worktrees / "probes"
        probes.mkdir(parents=True, exist_ok=True)
        scenarios = [
            ("git_ready_probe", "c16-ready", "GIT_READY", "ready"),
            ("signing_failure_probe", "c16-signing", "GIT_SIGNING_BLOCKED", "signing"),
            ("repository_hook_failure_probe", "c16-hook", "GIT_HOOK_BLOCKED", "hook"),
        ]
        trials: list[dict[str, Any]] = []
        checks: list[bool] = []
        model_checks: list[bool] = []
        for position, (name, run_id, expected, kind) in enumerate(scenarios, 1):
            hook: Path | None = None
            if kind == "signing":
                _signing_failure(source, worktrees / "support" / "fake-gpg")
            elif kind == "hook":
                _clear_signing(source)
                hook = _hook_failure(source)
            else:
                _clear_signing(source)
            outer, outer_error = _outer_probe(source, run_id + "-outer", probes)
            signing_diag = _diag(outer, ("gpg failed to sign", "signing failed", "failed to sign"))
            hook_diag = _diag(outer, ("pre-commit hook failed", "hook rejection", "hook failed"))
            outer_ok = (
                outer_error is None and outer.get("result") == expected
                and not outer.get("source_snapshot_changed") and not outer.get("cleanup_errors")
                and (kind != "signing" or signing_diag) and (kind != "hook" or hook_diag)
            )
            before = base.git_snapshot(source)
            payload = v2._run_trial(
                capability_id=cid,
                trial={"name": name, "sandbox": "workspace-write", "prompt": _c16_prompt(run_id, expected)},
                cwd=driver, snapshot_repo=source, schemas=schemas, results_dir=results,
                position=position, add_dir=worktrees, timeout=600,
            )
            after = base.git_snapshot(source)
            model_ok = payload.get("outcome") == "PASS" and before == after
            payload["outer_diagnostic_basis"] = {
                "expected_classification": expected,
                "outer_result_matches": outer.get("result") == expected,
                "source_snapshot_changed_empty": not bool(outer.get("source_snapshot_changed")),
                "cleanup_errors_empty": not bool(outer.get("cleanup_errors")),
                "signing_diagnostic_observed": signing_diag,
                "hook_diagnostic_observed": hook_diag,
                "outer_probe_error": outer_error,
            }
            trials.append(base.sanitize(payload))
            checks.append(outer_ok)
            model_checks.append(model_ok)
            if hook is not None:
                hook.unlink(missing_ok=True)
            if kind == "signing":
                _clear_signing(source)
    if not all(checks):
        result, met = "FAILED", False
        blocker = "A deterministic outer C16 classification/diagnostic/cleanup assertion failed."
    elif not all(model_checks):
        result, met = "BLOCKED", False
        blocker = "Deterministic C16 probes passed, but one matching live Codex invocation was incomplete."
    else:
        result, met, blocker = "REPRODUCED", True, None
    return _write_result(
        root=root, cap_runtime=cap_runtime, capability_id=cid, result=result,
        expected_met=met, observations=[f"outer_all_pass={str(all(checks)).lower()}", f"live_codex_all_pass={str(all(model_checks)).lower()}", "raw_diagnostics_retained=false"],
        blocker=blocker,
        summary=("C16 reproduced with deterministic diagnostic basis and matching live Codex probes." if met else "C16 did not fully reproduce after deterministic diagnostic verification."),
        trials=trials, fixture_commit=fixture_commit, version=version, os_name=os_name,
        source_commit=source_commit, date=date,
    )
