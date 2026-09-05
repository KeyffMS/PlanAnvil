from __future__ import annotations

import contextlib
import os
import shutil
import stat
from pathlib import Path
from typing import Any, Iterator

import live_codex_qualification_harness_v6 as v6

base = v6.base
compat = v6.compat
prior = v6.prior


def _runner_codex_home() -> Path:
    raw = os.environ.get("CODEX_HOME")
    return Path(raw).expanduser().resolve() if raw else (Path.home() / ".codex").resolve()


def _restore_file(path: Path, existed: bool, content: bytes, mode: int | None) -> None:
    if existed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        if mode is not None:
            path.chmod(mode)
    else:
        path.unlink(missing_ok=True)


@contextlib.contextmanager
def _live_runner_persisted_trust_runtime() -> Iterator[Path]:
    """Use the runner's real Codex auth while temporarily persisting project trust.

    C08/C09 run late enough in a full qualification that a copied/symlinked auth file can
    become stale while the runner's real Codex home refreshes credentials. Keep the live
    CODEX_HOME and change only config.toml, restoring it byte-for-byte afterwards.
    """

    home = _runner_codex_home()
    config_path = home / "config.toml"
    existed = config_path.exists()
    content = config_path.read_bytes() if existed else b""
    mode = stat.S_IMODE(config_path.stat().st_mode) if existed else None
    old_common = base.common_codex_args
    previous_home = os.environ.get("CODEX_HOME")

    def common_codex_args(**kwargs: Any) -> list[str]:
        cwd = Path(kwargs["cwd"]).resolve()
        compat._write_persisted_project_trust(home, cwd)
        kwargs["trust_project"] = False
        args = old_common(**kwargs)
        return [item for item in args if item != "--ignore-user-config"]

    base.common_codex_args = common_codex_args
    try:
        yield home
    finally:
        base.common_codex_args = old_common
        if previous_home is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = previous_home
        _restore_file(config_path, existed, content, mode)
        restored = config_path.exists() == existed
        if restored and existed:
            restored = config_path.read_bytes() == content
        if not restored:
            raise base.QualificationError(
                "Codex runner config.toml was not restored after persisted-trust qualification"
            )


def run_c08(**kwargs: Any):
    cap_runtime = Path(kwargs["runtime_root"]) / "C08"
    with (
        compat._codex0152_compaction(cap_runtime, "C08"),
        _live_runner_persisted_trust_runtime(),
    ):
        return compat.v4._c08_runtime(**kwargs)


def run_c09(**kwargs: Any):
    cap_runtime = Path(kwargs["runtime_root"]) / "C09"
    with (
        compat._codex0152_compaction(cap_runtime, "C09"),
        _live_runner_persisted_trust_runtime(),
    ):
        return compat.v4._c09_runtime(**kwargs)


def _seed_declared_project_fixture(repo: Path, context_proof: str) -> bool:
    """Use the same project-scoped role/hook shape that PlanAnvil targets."""

    v6._seed_project_fixture(repo, context_proof, include_project_agent=True)
    config_path = repo / ".codex" / "config.toml"
    text = config_path.read_text(encoding="utf-8")
    header = f"[agents.{v6.HOME_AGENT_NAME}]"
    if header not in text:
        text = text.rstrip() + (
            f"\n\n{header}\n"
            'description = "C13 qualification child for real SubagentStart context semantics."\n'
            f'config_file = "./agents/{v6.HOME_AGENT_FILENAME}"\n'
        )
        v6._write(config_path, text.rstrip() + "\n")
    return (repo / ".codex" / "agents" / v6.HOME_AGENT_FILENAME).is_file()


def _prepare_project_fallback_home(
    cap_runtime: Path,
    repo: Path,
) -> tuple[Path, Path | None, tuple[int, int, int] | None]:
    """Persist trust in an isolated home but keep the fallback role and hook project-scoped."""

    home, auth_path, auth_before = prior._prepare_isolated_codex_home(
        cap_runtime / "project-non-ephemeral"
    )
    compat._write_persisted_project_trust(home, repo)
    return home, auth_path, auth_before


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

        base.ensure_git_repo(project_repo)
        _seed_declared_project_fixture(project_repo, proof)
        project_fixture_commit = base.commit_fixture_baseline(project_repo)

        ephemeral_home, ephemeral_auth_path, ephemeral_auth_before = (
            v6._prepare_trusted_ephemeral_home(cap_runtime, project_repo)
        )
        ephemeral_cleanup_verified = True
        ephemeral_auth_unchanged = True
        prior._clear_hook_log(project_repo)
        before_ephemeral = base.git_snapshot(project_repo)
        try:
            payload_e, events_e, error_e, known_e = prior._run_c13_codex(
                repo=project_repo,
                schemas=schemas,
                results_dir=results_dir,
                position=1,
                ephemeral=True,
                isolated_codex_home=ephemeral_home,
                timeout=600,
            )
            after_ephemeral = base.git_snapshot(project_repo)
            records_e = prior._read_hook_records(project_repo)
        finally:
            ephemeral_cleanup_verified, ephemeral_auth_unchanged = (
                prior._cleanup_isolated_codex_home(
                    ephemeral_home,
                    ephemeral_auth_path,
                    ephemeral_auth_before,
                )
            )

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
        if known_e:
            outcome_e = "BLOCKED"
            trial_e["outcome"] = "BLOCKED"
            trial_e["blocker"] = "recognized ephemeral parent-thread registration failure"
        elif not (ephemeral_cleanup_verified and ephemeral_auth_unchanged):
            outcome_e = "BLOCKED"
            trial_e["outcome"] = "BLOCKED"
            trial_e["blocker"] = "isolated ephemeral CODEX_HOME cleanup/auth invariants failed"
        trial_e["agent_fixture_scope"] = "project"
        trial_e["agent_role_declared_explicitly"] = True
        trial_e["required_spawn_agent_type"] = v6.HOME_AGENT_NAME
        trial_e["persisted_project_trust"] = True
        trial_e["isolated_codex_home"] = True
        trial_e["isolated_home_cleanup_verified"] = ephemeral_cleanup_verified
        trial_e["auth_metadata_unchanged"] = ephemeral_auth_unchanged

        trials: list[dict[str, Any]] = [base.sanitize(trial_e)]
        fallback_used = False
        fallback_available = False
        cleanup_verified = True
        auth_unchanged = True
        project_agent_materialized = False
        fallback_fixture_commit: str | None = None

        if outcome_e == "PASS":
            final_outcome = "PASS"
            transport_resolution = "ephemeral"
        elif outcome_e == "FAILED":
            final_outcome = "FAILED"
            transport_resolution = "ephemeral_semantic_failure"
        elif not (known_e and v6.ALLOW_NON_EPHEMERAL_FALLBACK):
            final_outcome = "BLOCKED"
            transport_resolution = (
                "ephemeral_known_transport_blocker_fallback_not_enabled"
                if known_e
                else "ephemeral_unclassified_blocker"
            )
        else:
            fallback_used = True
            base.ensure_git_repo(fallback_repo)
            project_agent_materialized = _seed_declared_project_fixture(fallback_repo, proof)
            fallback_fixture_commit = base.commit_fixture_baseline(fallback_repo)

            isolated_home, auth_path, auth_before = _prepare_project_fallback_home(
                cap_runtime, fallback_repo
            )
            fallback_available = auth_path is not None and project_agent_materialized

            if not fallback_available:
                shutil.rmtree(isolated_home, ignore_errors=True)
                cleanup_verified = not isolated_home.exists()
                final_outcome = "BLOCKED"
                transport_resolution = "project_non_ephemeral_fallback_preflight_unavailable"
                trials.append(
                    {
                        "capability_id": capability_id,
                        "trial": "non_ephemeral_project_agent_fallback_preflight",
                        "trial_name": "non_ephemeral_project_agent_fallback_preflight",
                        "transport": "non-ephemeral",
                        "outcome": "BLOCKED",
                        "assertions": [],
                        "observations": [
                            f"project_agent_materialized={str(project_agent_materialized).lower()}",
                            f"file_backed_auth_bridge_available={str(auth_path is not None).lower()}",
                            "persisted_project_trust=true",
                            f"session_cleanup_verified={str(cleanup_verified).lower()}",
                        ],
                        "blocker": "project-scoped non-ephemeral fallback preflight unavailable",
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
                trial_n["agent_fixture_scope"] = "project"
                trial_n["project_agent_present"] = True
                trial_n["project_agent_declared_explicitly"] = True
                trial_n["home_agent_materialized"] = False
                trial_n["project_scoped_subagent_start_hook"] = True
                trial_n["required_spawn_agent_type"] = v6.HOME_AGENT_NAME
                trial_n["fallback_fixture_commit"] = fallback_fixture_commit
                trial_n["persisted_project_trust"] = True
                trials.append(base.sanitize(trial_n))
                final_outcome = outcome_n
                transport_resolution = "non_ephemeral_project_agent_fallback"

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
                "C13 reproduced through the controlled non-ephemeral project-agent "
                "fallback after the recognized ephemeral parent-thread registration "
                "failure; role and SubagentStart hook remained project-scoped."
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
            "C13 could not reach and verify the real project-scoped child startup semantics "
            "under the permitted Codex 0.152 qualification transport."
        )
        summary = (
            "C13 remains blocked because the real project-scoped SubagentStart semantic "
            "boundary was not completely exercised."
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
            "ephemeral_persisted_project_trust=true",
            f"ephemeral_cleanup_verified={str(ephemeral_cleanup_verified).lower()}",
            f"ephemeral_auth_metadata_unchanged={str(ephemeral_auth_unchanged).lower()}",
            f"non_ephemeral_fallback_enabled={str(v6.ALLOW_NON_EPHEMERAL_FALLBACK).lower()}",
            f"non_ephemeral_fallback_used={str(fallback_used).lower()}",
            f"non_ephemeral_fallback_available={str(fallback_available).lower()}",
            f"project_agent_materialized={str(project_agent_materialized).lower()}",
            f"session_cleanup_verified={str(cleanup_verified).lower()}",
            f"auth_metadata_unchanged={str(auth_unchanged).lower()}",
            f"transport_resolution={transport_resolution}",
            f"required_spawn_agent_type={v6.HOME_AGENT_NAME}",
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


def _install() -> None:
    v6.compat.run_c08 = run_c08
    v6.compat.run_c09 = run_c09
    v6._c13_runtime = _c13_runtime

    # C10 owns its fixture outside the model-authored generic planner. The live
    # lifecycle still runs through the product SessionStart/PreCompact/PostCompact
    # hooks and the product checkpoint validator.
    import live_codex_qualification_c10 as c10

    c10.install(v6, _live_runner_persisted_trust_runtime)


def main(argv: list[str] | None = None) -> int:
    _install()
    return v6.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
