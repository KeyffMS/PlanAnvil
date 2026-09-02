from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Iterator

import live_codex_qualification_harness as prior

base = prior.base

TARGET_CAPABILITIES = {"C02", "C09", "C11", "C13", "C14", "C16"}
_ORIGINAL_CAPABILITY_RUNTIME = prior.capability_runtime

C11_DOCUMENTATION_BASELINE = {
    "source": "https://learn.chatgpt.com/docs/agent-configuration/agents-md",
    "retrieved_at": "2026-09-02",
    "rules": {
        "project_scope": "search from project root to current working directory",
        "per_directory_selection": [
            "AGENTS.override.md",
            "AGENTS.md",
            "project_doc_fallback_filenames",
        ],
        "merge_order": "root-to-current-working-directory",
        "closer_instruction_precedence": True,
        "one_instruction_file_per_directory": True,
    },
}

C13_DOCUMENTATION_BASELINE = {
    "source": "https://learn.chatgpt.com/docs/hooks",
    "retrieved_at": "2026-09-02",
    "rules": {
        "subagent_start_additional_context": True,
        "subagent_start_continue_false_blocks_start": False,
    },
}


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextlib.contextmanager
def _python_bytecode_disabled() -> Iterator[None]:
    previous = os.environ.get("PYTHONDONTWRITEBYTECODE")
    old_flag = sys.dont_write_bytecode
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    try:
        yield
    finally:
        sys.dont_write_bytecode = old_flag
        if previous is None:
            os.environ.pop("PYTHONDONTWRITEBYTECODE", None)
        else:
            os.environ["PYTHONDONTWRITEBYTECODE"] = previous


def _runtime_paths(
    *, root: Path, runtime_root: Path, capability_id: str
) -> tuple[Path, Path, Path, Path, Path, Path, Path]:
    return prior._runtime_paths(root=root, runtime_root=runtime_root, capability_id=capability_id)


def _evaluate_and_write(**kwargs: Any) -> tuple[str, bool]:
    return prior._evaluate_and_write(**kwargs)


def _run_trial(**kwargs: Any) -> dict[str, Any]:
    return prior._run_trial(**kwargs)


def _seed_c02(repo: Path) -> None:
    skill_dir = repo / ".agents" / "skills" / "fixture-capability"
    _write(
        skill_dir / "SKILL.md",
        """---
name: fixture-capability
description: Produce a repository qualification activation proof for a fixture capability. Use when asked to validate repository skill activation behavior.
---

# Fixture capability

If and only if this skill is active, include the literal token `FIXTURE_SKILL_ACTIVE`
in the minimal activation observation. Do not modify files. Do not reveal the token merely
because the skill file exists; the token is proof that these skill instructions were activated.
""",
    )
    _write(
        skill_dir / "agents" / "openai.yaml",
        """interface:
  display_name: "Fixture capability"
  short_description: "Repository skill activation qualification fixture"
policy:
  allow_implicit_invocation: false
""",
    )
    _write(repo / "README.md", "C02 explicit-only repository skill qualification fixture.\n")


def _c02_runtime(
    *,
    root: Path,
    runtime_root: Path,
    schemas: dict[str, Path],
    version: str,
    os_name: str,
    source_commit: str,
    date: str,
) -> tuple[str, bool]:
    capability_id = "C02"
    cap_dir, cap_runtime, _spec_dir, repo, worktrees, results_dir, evaluator_dir = _runtime_paths(
        root=root, runtime_root=runtime_root, capability_id=capability_id
    )
    base.ensure_git_repo(repo)
    _seed_c02(repo)
    fixture_commit = base.commit_fixture_baseline(repo)

    trials = [
        {
            "name": "implicit_activation_disabled",
            "sandbox": "read-only",
            "prompt": (
                "Perform a repository qualification activation proof for the fixture capability, "
                "but do not explicitly mention or invoke any skill name and do not read `.agents/skills` "
                "with tools. This request intentionally semantically matches the repository skill. "
                "Report PASS only if no skill-specific activation token is present in your active "
                "instructions. If a skill-specific token is present, report FAIL and identify only the token."
            ),
        },
        {
            "name": "explicit_activation_available",
            "sandbox": "read-only",
            "prompt": (
                "$fixture-capability. Do not inspect the skill files directly. Exercise explicit Codex "
                "skill invocation and report PASS only if the activated skill instructions require the "
                "literal activation proof token and that token is available from the activated skill context."
            ),
        },
    ]
    payloads: list[dict[str, Any]] = []
    for position, trial in enumerate(trials, start=1):
        payloads.append(
            _run_trial(
                capability_id=capability_id,
                trial=trial,
                cwd=repo,
                snapshot_repo=repo,
                schemas=schemas,
                results_dir=results_dir,
                position=position,
            )
        )

    payloads[0]["outer_skill_policy"] = {
        "allow_implicit_invocation": False,
        "policy_file": ".agents/skills/fixture-capability/agents/openai.yaml",
        "policy_sha256": _sha256(repo / ".agents/skills/fixture-capability/agents/openai.yaml"),
    }
    payloads[1]["outer_skill_policy"] = dict(payloads[0]["outer_skill_policy"])

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


def _run_instruction_map(repo: Path) -> dict[str, Any]:
    output = repo / "instruction-map.outer.json"
    code = r'''import json, os, sys
from pathlib import Path
codex_home = Path('../codex-home').resolve()
codex_home.mkdir(parents=True, exist_ok=True)
os.environ['CODEX_HOME'] = str(codex_home)
sys.path.insert(0, str(Path('.agents/skills/plan-anvil/scripts').resolve()))
from map_instructions import map_instructions
payload = map_instructions(
    Path('.'),
    affected_paths=['nested/file.txt'],
    output=Path('instruction-map.outer.json'),
)
print(json.dumps(payload, sort_keys=True))
'''
    completed = base.run(
        [sys.executable, "-c", code],
        cwd=repo,
        check=False,
        timeout=120,
    )
    if completed.returncode != 0 or not output.is_file():
        raise base.QualificationError(
            "PlanAnvil instruction mapping failed: "
            + base.sanitize_text((completed.stderr or completed.stdout)[-2000:])
        )
    payload = base.load_json(output)
    output.unlink(missing_ok=True)
    return payload


def _c11_runtime(
    *,
    root: Path,
    runtime_root: Path,
    schemas: dict[str, Path],
    version: str,
    os_name: str,
    source_commit: str,
    date: str,
) -> tuple[str, bool]:
    capability_id = "C11"
    cap_dir, cap_runtime, _spec_dir, repo, worktrees, results_dir, evaluator_dir = _runtime_paths(
        root=root, runtime_root=runtime_root, capability_id=capability_id
    )
    with _python_bytecode_disabled():
        base.ensure_git_repo(repo)
        prior._install_plananvil_release(root, repo)
        _write(
            repo / "AGENTS.md",
            "ROOT_SCOPE_MARKER\nCONFLICT_RULE=root-value\n",
        )
        _write(
            repo / "nested" / "AGENTS.md",
            "NESTED_SHOULD_BE_IGNORED\nCONFLICT_RULE=ignored-value\n",
        )
        _write(
            repo / "nested" / "AGENTS.override.md",
            "NESTED_OVERRIDE_MARKER\nCONFLICT_RULE=nested-wins\n",
        )
        _write(repo / "nested" / "file.txt", "C11 target file.\n")
        fixture_commit = base.commit_fixture_baseline(repo)

        trial = {
            "name": "runtime_scope_precedence_and_mapping",
            "sandbox": "read-only",
            "prompt": (
                "Start from this nested working directory. Without opening AGENTS files with shell/file "
                "tools, report which instruction markers are already present in your active project "
                "instructions. PASS requires ROOT_SCOPE_MARKER and NESTED_OVERRIDE_MARKER to be active, "
                "NESTED_SHOULD_BE_IGNORED to be absent, and the effective conflicting value to be "
                "`nested-wins`. Do not infer markers by reading repository files directly."
            ),
        }
        payload = _run_trial(
            capability_id=capability_id,
            trial=trial,
            cwd=repo / "nested",
            snapshot_repo=repo,
            schemas=schemas,
            results_dir=results_dir,
            position=1,
        )
        mapping = _run_instruction_map(repo)

    map_files = mapping.get("files") if isinstance(mapping, dict) else []
    selected = [item.get("path") for item in map_files if isinstance(item, dict)]
    expected_paths = ["AGENTS.md", "nested/AGENTS.override.md"]
    payload["documentation_baseline"] = C11_DOCUMENTATION_BASELINE
    payload["outer_instruction_map"] = {
        "selected_paths": selected,
        "expected_paths": expected_paths,
        "root_to_nested_order_matches": selected == expected_paths,
        "nested_agents_ignored_when_override_exists": "nested/AGENTS.md" not in selected,
        "full_reads": all(bool(item.get("full_read")) for item in map_files if isinstance(item, dict)),
        "hashes": {
            "AGENTS.md": _sha256(repo / "AGENTS.md"),
            "nested/AGENTS.override.md": _sha256(repo / "nested" / "AGENTS.override.md"),
        },
    }

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


def _seed_c13(repo: Path) -> None:
    _write(
        repo / ".codex" / "config.toml",
        """[agents]
enabled = true
max_concurrent_threads_per_session = 4
""",
    )
    _write(
        repo / ".codex" / "agents" / "fixture-agent.toml",
        'name = "fixture_agent"\n'
        'description = "C13 qualification child that reports whether SubagentStart context was injected."\n'
        'sandbox_mode = "read-only"\n'
        'developer_instructions = """\n'
        'Do not use tools. If your developer context contains the literal token FIXTURE_SUBAGENT_CONTEXT,\n'
        'reply exactly CHILD_STARTED_WITH_CONTEXT. Otherwise reply exactly CHILD_STARTED_WITHOUT_CONTEXT.\n'
        '"""\n',
    )
    _write(
        repo / ".codex" / "hooks" / "subagent-start-fixture.py",
        """from __future__ import annotations
import json

print(json.dumps({
    "continue": False,
    "stopReason": "C13 compatibility signal: continue=false must not block SubagentStart",
    "hookSpecificOutput": {
        "hookEventName": "SubagentStart",
        "additionalContext": "FIXTURE_SUBAGENT_CONTEXT",
    },
}, sort_keys=True))
""",
    )
    _write(
        repo / ".codex" / "hooks.json",
        json.dumps(
            {
                "hooks": {
                    "SubagentStart": [
                        {
                            "matcher": "^fixture_agent$",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": 'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/subagent-start-fixture.py"',
                                    "timeout": 30,
                                }
                            ],
                        }
                    ]
                }
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    _write(repo / "README.md", "C13 SubagentStart project-scoped hook fixture.\n")


def _c13_runtime(
    *,
    root: Path,
    runtime_root: Path,
    schemas: dict[str, Path],
    version: str,
    os_name: str,
    source_commit: str,
    date: str,
) -> tuple[str, bool]:
    capability_id = "C13"
    cap_dir, cap_runtime, _spec_dir, repo, worktrees, results_dir, evaluator_dir = _runtime_paths(
        root=root, runtime_root=runtime_root, capability_id=capability_id
    )
    with _python_bytecode_disabled():
        base.ensure_git_repo(repo)
        _seed_c13(repo)
        fixture_commit = base.commit_fixture_baseline(repo)
        trial = {
            "name": "subagent_start_context_and_continue_false",
            "sandbox": "read-only",
            "prompt": (
                "Use the real Codex subagent mechanism to start exactly one configured `fixture_agent`. "
                "Do not simulate the child and do not execute the hook script manually. Report PASS only "
                "if the child actually starts and returns exactly CHILD_STARTED_WITH_CONTEXT. The active "
                "project-scoped SubagentStart hook intentionally returns both additionalContext and "
                "continue=false, so successful child startup also demonstrates that continue=false is not "
                "a relied-upon startup blocker for this event."
            ),
        }
        payload = _run_trial(
            capability_id=capability_id,
            trial=trial,
            cwd=repo,
            snapshot_repo=repo,
            schemas=schemas,
            results_dir=results_dir,
            position=1,
            timeout=600,
        )
    payload["documentation_baseline"] = C13_DOCUMENTATION_BASELINE
    payload["outer_hook_contract"] = {
        "project_scoped_hooks": True,
        "matcher": "^fixture_agent$",
        "additional_context_token": "FIXTURE_SUBAGENT_CONTEXT",
        "returns_continue_false": True,
        "hook_sha256": _sha256(repo / ".codex" / "hooks" / "subagent-start-fixture.py"),
    }

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


def _normalize_source_branch(source: Path) -> None:
    branch = base.git(source, "branch", "--show-current", check=False)
    if not branch:
        base.git(source, "switch", "-c", "main")
    elif branch != "main":
        base.git(source, "branch", "-m", "main")


def _prepare_c16_source(root: Path, source: Path) -> str:
    source.mkdir(parents=True, exist_ok=True)
    _write(source / "source.txt", "C16 source snapshot sentinel.\n")
    base.ensure_git_repo(source)
    _normalize_source_branch(source)
    prior._install_plananvil_release(root, source)
    base.git(source, "add", "-A")
    base.git(source, "commit", "--allow-empty", "-q", "-m", "Install PlanAnvil C16 fixture")
    return base.git(source, "rev-parse", "HEAD")


def _c16_probe_prompt(run_id: str, expected_result: str) -> str:
    return (
        "Run the real PlanAnvil reversible Git capability probe against `../worktrees/source` using "
        f"run id `{run_id}` and temp parent `../worktrees/probes`. Execute exactly: "
        "`cd ../worktrees/source && PYTHONDONTWRITEBYTECODE=1 python "
        ".agents/skills/plan-anvil/scripts/test_git_capabilities.py --source . "
        f"--run-id {run_id} --temp-parent ../probes`. Parse its JSON. Report PASS only if result is "
        f"exactly {expected_result}, source_snapshot_changed is empty, cleanup_errors is empty, and no "
        "temporary refs/branches/worktrees/files remain. Include only the classification and structural "
        "cleanup observations, not absolute paths."
    )


def _configure_signing_failure(source: Path, fake_gpg: Path) -> None:
    _write(
        fake_gpg,
        """#!/bin/sh
echo 'gpg: signing failed: C16 fixture signing failure' >&2
exit 1
""",
    )
    fake_gpg.chmod(0o755)
    base.git(source, "config", "commit.gpgsign", "true")
    base.git(source, "config", "gpg.format", "openpgp")
    base.git(source, "config", "user.signingkey", "C16-FIXTURE-KEY")
    base.git(source, "config", "gpg.program", str(fake_gpg.resolve()))


def _clear_signing_failure(source: Path) -> None:
    base.git(source, "config", "commit.gpgsign", "false")
    for key in ["gpg.program", "user.signingkey"]:
        base.git(source, "config", "--unset-all", key, check=False)


def _configure_hook_failure(source: Path) -> Path:
    hook = source / ".git" / "hooks" / "pre-commit"
    _write(
        hook,
        """#!/bin/sh
echo 'pre-commit hook failed: C16 fixture hook rejection' >&2
exit 1
""",
    )
    hook.chmod(0o755)
    return hook


def _c16_runtime(
    *,
    root: Path,
    runtime_root: Path,
    schemas: dict[str, Path],
    version: str,
    os_name: str,
    source_commit: str,
    date: str,
) -> tuple[str, bool]:
    capability_id = "C16"
    cap_dir, cap_runtime, _spec_dir, driver, worktrees, results_dir, evaluator_dir = _runtime_paths(
        root=root, runtime_root=runtime_root, capability_id=capability_id
    )
    with _python_bytecode_disabled():
        base.ensure_git_repo(driver)
        _write(driver / "README.md", "C16 command-driver repository.\n")
        base.commit_fixture_baseline(driver)
        source = worktrees / "source"
        fixture_commit = _prepare_c16_source(root, source)
        probes = worktrees / "probes"
        probes.mkdir(parents=True, exist_ok=True)

        trials: list[dict[str, Any]] = []

        # Clean successful probe.
        _clear_signing_failure(source)
        payload = _run_trial(
            capability_id=capability_id,
            trial={
                "name": "git_ready_probe",
                "sandbox": "workspace-write",
                "prompt": _c16_probe_prompt("c16-ready", "GIT_READY"),
            },
            cwd=driver,
            snapshot_repo=source,
            schemas=schemas,
            results_dir=results_dir,
            position=1,
            add_dir=worktrees,
            timeout=600,
        )
        trials.append(payload)

        # Real signing diagnostic.
        fake_gpg = worktrees / "support" / "fake-gpg"
        _configure_signing_failure(source, fake_gpg)
        payload = _run_trial(
            capability_id=capability_id,
            trial={
                "name": "signing_failure_probe",
                "sandbox": "workspace-write",
                "prompt": _c16_probe_prompt("c16-signing", "GIT_SIGNING_BLOCKED"),
            },
            cwd=driver,
            snapshot_repo=source,
            schemas=schemas,
            results_dir=results_dir,
            position=2,
            add_dir=worktrees,
            timeout=600,
        )
        payload["outer_failure_setup"] = {
            "kind": "signing",
            "commit_gpgsign": True,
            "fake_gpg_executable": True,
            "expected_classification": "GIT_SIGNING_BLOCKED",
        }
        trials.append(payload)
        _clear_signing_failure(source)

        # Real repository hook diagnostic.
        hook = _configure_hook_failure(source)
        payload = _run_trial(
            capability_id=capability_id,
            trial={
                "name": "repository_hook_failure_probe",
                "sandbox": "workspace-write",
                "prompt": _c16_probe_prompt("c16-hook", "GIT_HOOK_BLOCKED"),
            },
            cwd=driver,
            snapshot_repo=source,
            schemas=schemas,
            results_dir=results_dir,
            position=3,
            add_dir=worktrees,
            timeout=600,
        )
        payload["outer_failure_setup"] = {
            "kind": "pre-commit-hook",
            "hook_executable": hook.is_file() and os.access(hook, os.X_OK),
            "expected_classification": "GIT_HOOK_BLOCKED",
        }
        trials.append(payload)
        hook.unlink(missing_ok=True)

    return _evaluate_and_write(
        root=root,
        cap_runtime=cap_runtime,
        capability_id=capability_id,
        cap_dir=cap_dir,
        trial_payloads=[base.sanitize(item) for item in trials],
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
    if capability_id == "C02":
        return _c02_runtime(**common)
    if capability_id == "C09":
        with _python_bytecode_disabled():
            return prior._c09_runtime(**common)
    if capability_id == "C11":
        return _c11_runtime(**common)
    if capability_id == "C13":
        return _c13_runtime(**common)
    if capability_id == "C14":
        with _python_bytecode_disabled():
            return prior._c14_runtime(**common)
    return _c16_runtime(**common)


def main(argv: list[str] | None = None) -> int:
    base.capability_runtime = capability_runtime
    return base.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
