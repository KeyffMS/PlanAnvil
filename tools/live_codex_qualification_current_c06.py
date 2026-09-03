from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import live_codex_qualification as base
import live_codex_qualification_harness as v1
import live_codex_qualification_harness_v2 as v2
import live_codex_qualification_harness_v4 as v4
from live_codex_qualification_current_common import finish, runtime_paths


def _minimal_hook(log_rel: str) -> str:
    return f'''from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
payload = json.load(sys.stdin)
root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
log = root / {log_rel!r}
log.parent.mkdir(parents=True, exist_ok=True)
with log.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps({{"event":"PreToolUse","tool_name":payload.get("tool_name")}}, sort_keys=True) + "\\n")
'''


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _direct_patch(capability_id: str, repo: Path, target: str, content: str, schemas: dict[str, Path], results: Path, position: int) -> dict[str, Any]:
    return v2._run_trial(
        capability_id=capability_id,
        trial={
            "name": f"direct_apply_patch_{position}",
            "sandbox": "workspace-write",
            "prompt": (
                f"Use the direct apply_patch tool exactly once to create `{target}` containing `{content}` and a newline. "
                "Do not use shell redirection or another write tool. Do not inspect or invoke hook scripts manually. "
                "Return a minimal structured result."
            ),
        },
        cwd=repo,
        snapshot_repo=repo,
        schemas=schemas,
        results_dir=results,
        position=position,
    )


def run(*, root: Path, runtime_root: Path, schemas: dict[str, Path], version: str, os_name: str, source_commit: str, date: str) -> tuple[str, bool]:
    capability_id = "C06"
    _, cap_runtime, _, repo, _, results, _ = runtime_paths(root, runtime_root, capability_id)
    with v2._python_bytecode_disabled():
        # Layer 1: neutral Codex project hook.
        base.ensure_git_repo(repo)
        minimal_log = ".pursue/c06-minimal.jsonl"
        v2._write(repo / ".codex/hooks/minimal-c06.py", _minimal_hook(minimal_log))
        v2._write(
            repo / ".codex/hooks.json",
            json.dumps({"hooks": {"PreToolUse": [{"matcher": "^apply_patch$", "hooks": [{"type": "command", "command": 'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/minimal-c06.py"', "timeout": 30}]}]}}, indent=2, sort_keys=True) + "\n",
        )
        v2._write(repo / ".gitignore", minimal_log + "\n")
        v2._write(repo / "README.md", "C06 minimal hook fixture.\n")
        fixture_commit = base.commit_fixture_baseline(repo)
        minimal_payload = _direct_patch(capability_id, repo, ".pursue/c06-minimal.txt", "C06_MINIMAL", schemas, results, 1)
        minimal_events = [record for record in _read_jsonl(repo / minimal_log) if record.get("event") == "PreToolUse" and record.get("tool_name") == "apply_patch"]
        minimal_file = repo / ".pursue/c06-minimal.txt"
        minimal_mutation = minimal_file.is_file() and minimal_file.read_text(encoding="utf-8").strip() == "C06_MINIMAL"

        # Layer 2: real PlanAnvil guard.
        guard = cap_runtime / "guard-repo"
        base.ensure_git_repo(guard)
        v1._install_plananvil_release(root, guard)
        v4._instrument_hooks(guard, event_to_script={"PreToolUse": "plan-anvil-guard.py"})
        v2._write(guard / "README.md", "C06 PlanAnvil guard fixture.\n")
        guard_commit = base.commit_fixture_baseline(guard)
        v4._clear_hook_log(guard)
        guard_payload = _direct_patch(capability_id, guard, ".pursue/c06-guard.txt", "C06_GUARD", schemas, results, 2)
        guard_events = [record for record in v4._read_hook_records(guard) if record.get("event") == "PreToolUse" and record.get("tool_name") == "apply_patch"]

        # Layer 3: deterministic outside-hook mutation must be caught by Git postconditions.
        before_count = len(v4._read_hook_records(guard))
        with (guard / "README.md").open("a", encoding="utf-8") as handle:
            handle.write("C06_OUTSIDE_HOOK_LIFECYCLE\n")
        status = base.git(guard, "status", "--porcelain=v1", "--untracked-files=all")
        postcondition = any(line.endswith("README.md") for line in status.splitlines())
        count_unchanged = len(v4._read_hook_records(guard)) == before_count

    if minimal_mutation and not minimal_events:
        result, blocker = "FAILED", "A real direct apply_patch completed under a minimal matching project PreToolUse hook, but the hook did not run."
    elif not minimal_mutation:
        result, blocker = "BLOCKED", "The minimal direct apply_patch layer did not complete the requested mutation."
    elif not guard_events:
        result, blocker = "FAILED", "Minimal Codex PreToolUse worked but the actual PlanAnvil guard route did not observe direct apply_patch."
    elif not (postcondition and count_unchanged):
        result, blocker = "FAILED", "Mandatory Git postcondition detection did not catch the outside-hook mutation."
    else:
        result, blocker = "REPRODUCED", None

    return finish(
        root=root,
        cap_runtime=cap_runtime,
        capability_id=capability_id,
        result=result,
        observations=[
            f"minimal_apply_patch_mutation={str(minimal_mutation).lower()}",
            f"minimal_pretooluse_events={len(minimal_events)}",
            f"plananvil_pretooluse_events={len(guard_events)}",
            f"git_postcondition_detected={str(postcondition).lower()}",
        ],
        blocker=blocker,
        summary="C06 isolates Codex hook coverage, PlanAnvil guard routing and outside-hook postcondition defense as separate assertions.",
        trials=[
            {**base.sanitize(minimal_payload), "layer": "minimal_codex_hook", "matching_pretooluse_events": len(minimal_events)},
            {**base.sanitize(guard_payload), "layer": "plananvil_guard", "fixture_commit": guard_commit, "matching_pretooluse_events": len(guard_events)},
            {"capability_id": capability_id, "trial": "outer_postcondition", "outcome": "PASS" if postcondition and count_unchanged else "FAIL", "assertions": [], "observations": [f"postcondition={str(postcondition).lower()}", f"hook_count_unchanged={str(count_unchanged).lower()}"], "blocker": None},
        ],
        fixture_commit=fixture_commit,
        version=version,
        os_name=os_name,
        source_commit=source_commit,
        date=date,
    )
