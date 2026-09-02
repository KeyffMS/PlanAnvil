from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import live_codex_qualification_harness_v2 as prior

base = prior.base

TARGET_CAPABILITIES = {"C12"}
_ORIGINAL_CAPABILITY_RUNTIME = prior.capability_runtime

C12_LIMIT_BYTES = 1024
C12_FIXTURE_BYTES = 4320
C12_TAIL_OFFSET = 3072


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_agents_fixture(head_value: str, tail_value: str) -> bytes:
    prefix = f"C12_HEAD_TOKEN={head_value}\n".encode("utf-8")
    tail = f"\nC12_TAIL_TOKEN={tail_value}\n".encode("utf-8")
    if len(prefix) >= C12_LIMIT_BYTES:
        raise ValueError("C12 head marker must fit inside the automatic instruction budget")
    if len(prefix) >= C12_TAIL_OFFSET or C12_TAIL_OFFSET + len(tail) > C12_FIXTURE_BYTES:
        raise ValueError("C12 marker layout is invalid")
    payload = prefix + (b"A" * (C12_TAIL_OFFSET - len(prefix))) + tail
    payload += b"B" * (C12_FIXTURE_BYTES - len(payload))
    if len(payload) != C12_FIXTURE_BYTES:
        raise AssertionError("C12 fixture size mismatch")
    return payload


def _runtime_paths(
    *, root: Path, runtime_root: Path, capability_id: str
) -> tuple[Path, Path, Path, Path, Path, Path, Path]:
    return prior._runtime_paths(root=root, runtime_root=runtime_root, capability_id=capability_id)


def _run_c12_codex_probe(
    *,
    repo: Path,
    schemas: dict[str, Path],
    results_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    output = results_dir / "trial-01.json"
    output.unlink(missing_ok=True)
    args = base.common_codex_args(
        cwd=repo,
        sandbox="read-only",
        schema=schemas["trial"],
        output=output,
        trust_project=True,
        hook_trust=False,
        ignore_rules=False,
    )
    args += ["-c", f"project_doc_max_bytes={C12_LIMIT_BYTES}"]
    args.append(
        """Execute C12 automatic project-instruction budget qualification.

Do not run shell commands, do not use tools, and do not open AGENTS.md. Use only project
instructions that Codex supplied automatically before this user message.

Report the exact value following `C12_HEAD_TOKEN=` if that assignment is present in the
automatically supplied project instructions. Report the exact value following
`C12_TAIL_TOKEN=` only if that assignment is also present; otherwise state that the tail
assignment is not present. Never guess a token value.

Return capability_id C12, trial automatic_instruction_budget, and minimal assertions and
observations needed to record what was actually visible automatically."""
    )
    try:
        completed = base.run(args, cwd=repo, check=False, timeout=300)
    except subprocess.TimeoutExpired:
        return {}, {"timeout": True}, "Codex invocation timed out"
    events = base.event_summary(completed.stdout)
    if completed.returncode != 0:
        return {}, events, f"Codex exited {completed.returncode}: {base.sanitize_text(completed.stderr[-2500:])}"
    if not output.is_file():
        return {}, events, "Codex did not produce the structured output file"
    try:
        payload = base.load_json(output)
    except (OSError, json.JSONDecodeError) as exc:
        return {}, events, f"Codex produced invalid structured output: {exc}"
    if not isinstance(payload, dict):
        return {}, events, "Codex structured output was not a JSON object"
    return base.sanitize(payload), events, None


def _run_plananvil_full_read(
    *, root: Path, cap_runtime: Path, repo: Path
) -> tuple[dict[str, Any], str | None]:
    output = repo / "c12-instruction-map.json"
    output.unlink(missing_ok=True)
    codex_home = cap_runtime / "empty-codex-home"
    codex_home.mkdir(parents=True, exist_ok=True)
    scripts = root / ".agents" / "skills" / "plan-anvil" / "scripts"
    helper = "\n".join(
        [
            "import json, sys",
            "from pathlib import Path",
            f"sys.path.insert(0, {str(scripts)!r})",
            "from map_instructions import map_instructions",
            f"repo = Path({str(repo)!r})",
            "result = map_instructions(",
            "    repo,",
            "    affected_paths=['src/file.txt'],",
            "    output=repo / 'c12-instruction-map.json',",
            f"    automatic_byte_limit={C12_LIMIT_BYTES},",
            "    require_scaffolded_output=False,",
            ")",
            "print(json.dumps(result, sort_keys=True))",
        ]
    )
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-B", "-c", helper],
        cwd=repo,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        return {}, f"PlanAnvil map_instructions failed: {base.sanitize_text(completed.stderr[-2000:])}"
    if not output.is_file():
        return {}, "PlanAnvil map_instructions did not create instruction-map evidence"
    try:
        mapped = base.load_json(output)
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"PlanAnvil instruction-map evidence was invalid: {exc}"
    output.unlink(missing_ok=True)
    if not isinstance(mapped, dict):
        return {}, "PlanAnvil instruction-map evidence was not an object"
    entries = mapped.get("files")
    if not isinstance(entries, list):
        return {}, "PlanAnvil instruction-map evidence did not contain files"
    entry = next((item for item in entries if isinstance(item, dict) and item.get("path") == "AGENTS.md"), None)
    if not isinstance(entry, dict):
        return {}, "PlanAnvil instruction-map evidence did not contain AGENTS.md"
    return base.sanitize(
        {
            "automatic_byte_limit": mapped.get("automatic_byte_limit"),
            "path": entry.get("path"),
            "bytes": entry.get("bytes"),
            "sha256": entry.get("sha256"),
            "full_read": entry.get("full_read"),
            "truncation_risk": entry.get("truncation_risk"),
        }
    ), None


def _c12_runtime(
    *,
    root: Path,
    runtime_root: Path,
    schemas: dict[str, Path],
    version: str,
    os_name: str,
    source_commit: str,
    date: str,
) -> tuple[str, bool]:
    capability_id = "C12"
    cap_dir, cap_runtime, spec_dir, repo, worktrees, results_dir, evaluator_dir = _runtime_paths(
        root=root, runtime_root=runtime_root, capability_id=capability_id
    )
    del cap_dir, spec_dir, worktrees, evaluator_dir

    base.ensure_git_repo(repo)
    head_value = hashlib.sha256(f"{source_commit}:C12:HEAD".encode("utf-8")).hexdigest()[:24]
    tail_value = hashlib.sha256(f"{source_commit}:C12:TAIL".encode("utf-8")).hexdigest()[:24]
    fixture = _build_agents_fixture(head_value, tail_value)
    agents_path = repo / "AGENTS.md"
    agents_path.write_bytes(fixture)
    _write(repo / ".codex" / "config.toml", f"project_doc_max_bytes = {C12_LIMIT_BYTES}\n")
    _write(repo / "src" / "file.txt", "C12 affected file.\n")
    _write(repo / "README.md", "C12 deterministic project instruction byte-budget fixture.\n")
    fixture_commit = base.commit_fixture_baseline(repo)

    before = base.git_snapshot(repo)
    payload, events, invocation_error = _run_c12_codex_probe(
        repo=repo,
        schemas=schemas,
        results_dir=results_dir,
    )
    after = base.git_snapshot(repo)

    serialized = json.dumps(payload, sort_keys=True)
    command_items = int(events.get("completed_command_items") or 0)
    head_observed = head_value in serialized
    tail_observed = tail_value in serialized

    if invocation_error:
        automatic_outcome = "BLOCKED"
        automatic_blocker = invocation_error
    elif command_items != 0:
        automatic_outcome = "BLOCKED"
        automatic_blocker = "C12 automatic-loading probe used command tools, so automatic visibility cannot be isolated."
    elif not head_observed:
        automatic_outcome = "BLOCKED"
        automatic_blocker = "C12 head marker inside the first 1024 bytes was not evidenced by the tool-free response."
    elif tail_observed:
        automatic_outcome = "FAIL"
        automatic_blocker = "C12 tail marker beyond the 1024-byte budget was automatically visible."
    else:
        automatic_outcome = "PASS"
        automatic_blocker = None

    automatic_trial = {
        "capability_id": capability_id,
        "trial": "automatic_instruction_budget",
        "trial_name": "automatic_instruction_budget",
        "outcome": automatic_outcome,
        "assertions": [
            {
                "name": "automatic_instruction_loading_is_budget_limited",
                "status": automatic_outcome,
                "evidence": (
                    f"fixture_bytes={C12_FIXTURE_BYTES}; limit_bytes={C12_LIMIT_BYTES}; "
                    f"head_marker_observed={str(head_observed).lower()}; "
                    f"tail_marker_observed={str(tail_observed).lower()}; "
                    f"completed_command_items={command_items}"
                ),
            }
        ],
        "observations": [
            f"project_config_limit={C12_LIMIT_BYTES}",
            f"cli_override_limit={C12_LIMIT_BYTES}",
            f"fixture_bytes={C12_FIXTURE_BYTES}",
            "head_marker_offset_before_limit=true",
            f"tail_marker_offset={C12_TAIL_OFFSET}",
            f"head_marker_observed={str(head_observed).lower()}",
            f"tail_marker_observed={str(tail_observed).lower()}",
            f"completed_command_items={command_items}",
        ],
        "blocker": automatic_blocker,
        "sandbox": "read-only",
        "event_summary": events,
        "git_before": before,
        "git_after": after,
        "config_evidence": {
            "project_config_path": ".codex/config.toml",
            "project_config_sha256": "sha256:" + hashlib.sha256((repo / ".codex" / "config.toml").read_bytes()).hexdigest(),
            "project_doc_max_bytes": C12_LIMIT_BYTES,
            "runtime_cli_override": f"project_doc_max_bytes={C12_LIMIT_BYTES}",
        },
    }

    mapped, map_error = _run_plananvil_full_read(root=root, cap_runtime=cap_runtime, repo=repo)
    expected_hash = "sha256:" + hashlib.sha256(agents_path.read_bytes()).hexdigest()
    map_ok = (
        map_error is None
        and mapped.get("automatic_byte_limit") == C12_LIMIT_BYTES
        and mapped.get("bytes") == C12_FIXTURE_BYTES
        and mapped.get("sha256") == expected_hash
        and mapped.get("full_read") is True
        and mapped.get("truncation_risk") is True
    )
    explicit_trial = {
        "capability_id": capability_id,
        "trial": "plananvil_explicit_full_file_hash",
        "trial_name": "plananvil_explicit_full_file_hash",
        "outcome": "PASS" if map_ok else ("BLOCKED" if map_error else "FAIL"),
        "assertions": [
            {
                "name": "plananvil_explicit_read_hash_covers_complete_fixture",
                "status": "PASS" if map_ok else ("BLOCKED" if map_error else "FAIL"),
                "evidence": (
                    f"bytes={mapped.get('bytes')}; full_read={mapped.get('full_read')}; "
                    f"truncation_risk={mapped.get('truncation_risk')}; hash_matches={str(mapped.get('sha256') == expected_hash).lower()}"
                    if not map_error
                    else map_error
                ),
            }
        ],
        "observations": [
            f"fixture_bytes={C12_FIXTURE_BYTES}",
            f"expected_sha256={expected_hash}",
            f"map_error={map_error or 'none'}",
            *([json.dumps(mapped, sort_keys=True)] if mapped else []),
        ],
        "blocker": map_error,
        "execution": "outer deterministic PlanAnvil map_instructions",
    }

    if automatic_outcome == "BLOCKED" or explicit_trial["outcome"] == "BLOCKED":
        result = "BLOCKED"
        expected_met = False
        blocker = automatic_blocker or map_error or "C12 evidence was incomplete."
        summary = "C12 blocked because the deterministic runtime probe could not isolate both required assertions."
    elif automatic_outcome == "FAIL" or explicit_trial["outcome"] == "FAIL":
        result = "FAILED"
        expected_met = False
        blocker = automatic_blocker or "PlanAnvil explicit full-file read/hash did not match the fixture."
        summary = "C12 failed because observed runtime behavior contradicted the project instruction byte-budget contract."
    else:
        result = "REPRODUCED"
        expected_met = True
        blocker = None
        summary = "C12 reproduced: automatic project instructions respected the 1024-byte budget while PlanAnvil explicitly read and hashed the complete 4320-byte fixture."

    observations = [
        f"automatic_outcome={automatic_outcome}",
        f"head_marker_observed={str(head_observed).lower()}",
        f"tail_marker_observed={str(tail_observed).lower()}",
        f"completed_command_items={command_items}",
        f"plananvil_full_read_ok={str(map_ok).lower()}",
    ]
    required = base.write_evidence(
        root=root,
        capability_id=capability_id,
        result=result,
        expected_met=expected_met,
        observations=observations,
        blocker=blocker,
        summary=summary,
        trials=[base.sanitize(automatic_trial), base.sanitize(explicit_trial)],
        fixture_commit=fixture_commit,
        version=version,
        os_name=os_name,
        source_commit=source_commit,
        date=date,
    )
    base.local_commit(root, capability_id)
    shutil.rmtree(cap_runtime, ignore_errors=True)
    return result, required


def capability_runtime(**kwargs: Any) -> tuple[str, bool]:
    capability_id = str(kwargs["capability_id"])
    if capability_id not in TARGET_CAPABILITIES:
        return _ORIGINAL_CAPABILITY_RUNTIME(**kwargs)
    common = {key: value for key, value in kwargs.items() if key != "capability_id"}
    return _c12_runtime(**common)


def main(argv: list[str] | None = None) -> int:
    base.capability_runtime = capability_runtime
    return base.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
