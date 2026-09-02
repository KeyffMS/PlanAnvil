from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import live_codex_qualification_harness_v5 as prior

base = prior.base

TARGET_CAPABILITIES = {"C13"}
_ORIGINAL_CAPABILITY_RUNTIME = prior.capability_runtime
ALLOW_NON_EPHEMERAL_FALLBACK = False
HOME_AGENT_NAME = "fixture_agent"
HOME_AGENT_FILENAME = "fixture_agent.toml"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _agent_toml() -> str:
    return (
        f'name = "{HOME_AGENT_NAME}"\n'
        'description = "C13 qualification child for real SubagentStart context semantics."\n'
        'sandbox_mode = "read-only"\n'
        'developer_instructions = """\n'
        'Do not use tools. Inspect only your already-active startup/developer context.\n'
        f'If it contains a line beginning `{prior.C13_CONTEXT_PREFIX}`, reply exactly\n'
        f'`{prior.C13_ECHO_PREFIX}<value>` where <value> is the exact opaque value after the equals sign.\n'
        f'If no such line is present, reply exactly `{prior.C13_MISSING}`. Never guess a value.\n'
        '"""\n'
    )


def _seed_project_fixture(repo: Path, context_proof: str, *, include_project_agent: bool) -> None:
    _write(
        repo / ".codex" / "config.toml",
        """[agents]
enabled = true
max_concurrent_threads_per_session = 2
""",
    )
    if include_project_agent:
        _write(repo / ".codex" / "agents" / HOME_AGENT_FILENAME, _agent_toml())

    _write(
        repo / ".codex" / "hooks" / "subagent-start-fixture.py",
        "from __future__ import annotations\n"
        "import json\n\n"
        "print(json.dumps({\n"
        '    "continue": False,\n'
        '    "stopReason": "C13 compatibility signal: continue=false must not block SubagentStart",\n'
        '    "hookSpecificOutput": {\n'
        '        "hookEventName": "SubagentStart",\n'
        f'        "additionalContext": "{prior.C13_CONTEXT_PREFIX}{context_proof}",\n'
        "    },\n"
        "}, sort_keys=True))\n",
    )
    _write(
        repo / ".codex" / "hooks" / "qualification-c13-hook-proxy.py",
        prior._c13_hook_proxy_source(),
    )
    _write(
        repo / ".codex" / "hooks.json",
        json.dumps(
            {
                "hooks": {
                    "SubagentStart": [
                        {
                            "matcher": f"^{HOME_AGENT_NAME}$",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": (
                                        'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/'
                                        'qualification-c13-hook-proxy.py"'
                                    ),
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
    scope = "project-agent" if include_project_agent else "project-hook-only"
    _write(repo / "README.md", f"C13 deterministic {scope} qualification fixture.\n")
    gitignore = repo / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if prior.C13_HOOK_LOG_RELATIVE not in existing:
        with gitignore.open("a", encoding="utf-8") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            handle.write(prior.C13_HOOK_LOG_RELATIVE + "\n")


def _prepare_home_scoped_fallback_agent(
    cap_runtime: Path,
) -> tuple[Path, Path | None, tuple[int, int, int] | None, bool]:
    home, auth_path, auth_before = prior._prepare_isolated_codex_home(cap_runtime)
    agent_path = home / "agents" / HOME_AGENT_FILENAME
    _write(agent_path, _agent_toml())
    return home, auth_path, auth_before, agent_path.is_file()


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
    (
        _cap_dir,
        cap_runtime,
        _spec_dir,
        project_repo,
        _worktrees,
        results_dir,
        _evaluator_dir,
    ) = prior._runtime_paths(root=root, runtime_root=runtime_root, capability_id=capability_id)
    fallback_repo = cap_runtime / "fallback-repo"

    with prior.prior.v2._python_bytecode_disabled():
        proof = prior._context_proof(source_commit)

        # Attempt 1 remains project-scoped and ephemeral. Filename, declared name,
        # prompt target, and hook matcher are deliberately identical.
        base.ensure_git_repo(project_repo)
        _seed_project_fixture(project_repo, proof, include_project_agent=True)
        project_fixture_commit = base.commit_fixture_baseline(project_repo)

        prior._clear_hook_log(project_repo)
        before_ephemeral = base.git_snapshot(project_repo)
        payload_e, events_e, error_e, known_e = prior._run_c13_codex(
            repo=project_repo,
            schemas=schemas,
            results_dir=results_dir,
            position=1,
            ephemeral=True,
            timeout=600,
        )
        after_ephemeral = base.git_snapshot(project_repo)
        records_e = prior._read_hook_records(project_repo)
        outcome_e, trial_e = prior._evaluate_transport(
            transport="ephemeral",
            payload=payload_e,
            events=events_e,
            error=error_e,
            known_parent_failure=known_e,
            records=records_e,
            context_proof=proof,
            git_before=before_ephemeral,
            git_after=after_ephemeral,
        )
        trial_e["agent_fixture_scope"] = "project"
        trial_e["agent_name_matches_filename"] = True

        trials: list[dict[str, Any]] = [base.sanitize(trial_e)]
        fallback_used = False
        fallback_available = False
        cleanup_verified = True
        auth_unchanged = True
        home_agent_materialized = False
        fallback_fixture_commit: str | None = None

        if outcome_e == "PASS":
            final_outcome = "PASS"
            transport_resolution = "ephemeral"
        elif outcome_e == "FAILED":
            final_outcome = "FAILED"
            transport_resolution = "ephemeral_semantic_failure"
        elif not (known_e and ALLOW_NON_EPHEMERAL_FALLBACK):
            final_outcome = "BLOCKED"
            transport_resolution = (
                "ephemeral_known_transport_blocker_fallback_not_enabled"
                if known_e
                else "ephemeral_unclassified_blocker"
            )
        else:
            # Run #8 proved that non-ephemeral registration survives the parent-thread
            # failure but the project-scoped synthetic agent can still be rejected before
            # SubagentStart. Baseline 2.3 therefore isolates the semantic probe from that
            # independent discovery limitation: the synthetic child is home-scoped inside
            # a disposable CODEX_HOME while the hook under test remains project-scoped.
            fallback_used = True
            base.ensure_git_repo(fallback_repo)
            _seed_project_fixture(fallback_repo, proof, include_project_agent=False)
            fallback_fixture_commit = base.commit_fixture_baseline(fallback_repo)

            isolated_home, auth_path, auth_before, home_agent_materialized = (
                _prepare_home_scoped_fallback_agent(cap_runtime)
            )
            fallback_available = auth_path is not None and home_agent_materialized

            if not fallback_available:
                shutil.rmtree(isolated_home, ignore_errors=True)
                cleanup_verified = not isolated_home.exists()
                final_outcome = "BLOCKED"
                transport_resolution = "isolated_non_ephemeral_fallback_preflight_unavailable"
                trials.append(
                    {
                        "capability_id": capability_id,
                        "trial": "non_ephemeral_home_agent_fallback_preflight",
                        "trial_name": "non_ephemeral_home_agent_fallback_preflight",
                        "transport": "non-ephemeral",
                        "outcome": "BLOCKED",
                        "assertions": [],
                        "observations": [
                            "home_scoped_fixture_agent_materialized="
                            f"{str(home_agent_materialized).lower()}",
                            "file_backed_auth_bridge_available="
                            f"{str(auth_path is not None).lower()}",
                            f"session_cleanup_verified={str(cleanup_verified).lower()}",
                        ],
                        "blocker": "isolated non-ephemeral home-agent fallback preflight unavailable",
                    }
                )
            else:
                prior._clear_hook_log(fallback_repo)
                before_fallback = base.git_snapshot(fallback_repo)
                payload_n: dict[str, Any] = {}
                events_n: dict[str, Any] = {}
                error_n: str | None = None
                known_n = False
                session_rollouts = 0
                after_fallback = before_fallback
                records_n: list[dict[str, Any]] = []
                try:
                    payload_n, events_n, error_n, known_n = prior._run_c13_codex(
                        repo=fallback_repo,
                        schemas=schemas,
                        results_dir=results_dir,
                        position=2,
                        ephemeral=False,
                        isolated_codex_home=isolated_home,
                        timeout=600,
                    )
                    session_rollouts = prior._session_rollout_count(isolated_home)
                    after_fallback = base.git_snapshot(fallback_repo)
                    records_n = prior._read_hook_records(fallback_repo)
                finally:
                    cleanup_verified, auth_unchanged = prior._cleanup_isolated_codex_home(
                        isolated_home,
                        auth_path,
                        auth_before,
                    )

                outcome_n, trial_n = prior._evaluate_transport(
                    transport="non-ephemeral",
                    payload=payload_n,
                    events=events_n,
                    error=error_n,
                    known_parent_failure=known_n,
                    records=records_n,
                    context_proof=proof,
                    git_before=before_fallback,
                    git_after=after_fallback,
                    session_rollouts_created=session_rollouts,
                    session_cleanup_verified=cleanup_verified,
                    auth_unchanged=auth_unchanged,
                )
                trial_n["agent_fixture_scope"] = "disposable_CODEX_HOME"
                trial_n["project_agent_present"] = False
                trial_n["home_agent_materialized"] = home_agent_materialized
                trial_n["project_scoped_subagent_start_hook"] = True
                trial_n["agent_name_matches_filename"] = True
                trial_n["fallback_fixture_commit"] = fallback_fixture_commit
                trials.append(base.sanitize(trial_n))
                final_outcome = outcome_n
                transport_resolution = "non_ephemeral_home_agent_fallback"

    if final_outcome == "PASS":
        result = "REPRODUCED"
        expected_met = True
        blocker = None
        if transport_resolution == "ephemeral":
            summary = (
                "C13 reproduced directly under ephemeral execution with one real "
                "SubagentStart hook and child context echo."
            )
        else:
            summary = (
                "C13 reproduced through the baseline 2.3 controlled non-ephemeral "
                "home-agent fallback after the recognized ephemeral parent-thread "
                "registration failure; the SubagentStart hook remained project-scoped."
            )
    elif final_outcome == "FAILED":
        result = "FAILED"
        expected_met = False
        blocker = (
            "C13 reached real SubagentStart startup but observed semantics contradicted "
            "the expected context/continue=false contract."
        )
        summary = "C13 failed after reaching the real SubagentStart semantic boundary."
    else:
        result = "BLOCKED"
        expected_met = False
        blocker = (
            "C13 could not reach and verify the real child startup semantics under the "
            "baseline 2.3 permitted qualification transport."
        )
        summary = (
            "C13 remains blocked because the real SubagentStart semantic boundary was "
            "not completely exercised."
        )

    evidence_fixture_commit = (
        fallback_fixture_commit if fallback_used and fallback_fixture_commit else project_fixture_commit
    )
    return prior.prior._write_result(
        root=root,
        cap_runtime=cap_runtime,
        capability_id=capability_id,
        result=result,
        expected_met=expected_met,
        observations=[
            f"ephemeral_outcome={outcome_e}",
            f"ephemeral_known_parent_thread_failure={str(known_e).lower()}",
            f"non_ephemeral_fallback_enabled={str(ALLOW_NON_EPHEMERAL_FALLBACK).lower()}",
            f"non_ephemeral_fallback_used={str(fallback_used).lower()}",
            f"non_ephemeral_fallback_available={str(fallback_available).lower()}",
            f"home_scoped_fixture_agent_materialized={str(home_agent_materialized).lower()}",
            "fallback_project_agent_present=false" if fallback_used else "fallback_not_used=true",
            f"session_cleanup_verified={str(cleanup_verified).lower()}",
            f"auth_metadata_unchanged={str(auth_unchanged).lower()}",
            f"transport_resolution={transport_resolution}",
        ],
        blocker=blocker,
        summary=summary,
        trials=trials,
        fixture_commit=evidence_fixture_commit,
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
    return _c13_runtime(**common)


def main(argv: list[str] | None = None) -> int:
    global ALLOW_NON_EPHEMERAL_FALLBACK
    args = list(sys.argv[1:] if argv is None else argv)
    allow_flag = "--allow-c13-non-ephemeral-fallback"
    ALLOW_NON_EPHEMERAL_FALLBACK = allow_flag in args
    args = [item for item in args if item != allow_flag]

    # The v5 C13-only controller is still useful as a short diagnostic surface,
    # but baseline 2.3 also permits the same narrowly gated fallback in full mode.
    base.capability_runtime = capability_runtime
    prior.capability_runtime = capability_runtime
    if "--only" in args:
        if not ALLOW_NON_EPHEMERAL_FALLBACK:
            raise base.QualificationError(
                "C13-only qualification requires --allow-c13-non-ephemeral-fallback"
            )
        return prior._c13_only_main(args)
    return base.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
