from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import live_codex_qualification as base
import live_codex_qualification_harness_v2 as v2
from live_codex_qualification_current_common import finish, runtime_paths


def _contract_text(*, valid: bool) -> str:
    topology = (
        "The execution topology is flat direct-child; descendants must not spawn descendants."
        if valid
        else "The execution topology is nested and relies on agents.max_depth = 4."
    )
    return f"""# C03 execution contract

Jim and Jenny coordinate an implementation agent and an independent verifier.
Winston Wolfe performs final independent verification.
{topology}
Only one agent modifies files at a time.

STRATEGY-A ATTEMPT-A1 ATTEMPT-A2 ATTEMPT-A3
STRATEGY-B ATTEMPT-B1 ATTEMPT-B2 ATTEMPT-B3
After six implementation failures, stop.

Task branch `pursue/task/C03/fixture`
Integration branch `pursue/integration/C03/fixture`

## Testing and independent verification

GREEN BASELINE -> EXPECTED RED -> IMPLEMENTATION -> FULL GREEN -> INDEPENDENT VERIFICATION.

## Production verification, switching, and approvals

Explicit user approval is required before a base merge or push, before live switching,
and before any irreversible operation.
"""


def _load_execution_contract(root: Path) -> Any:
    path = root / ".agents/skills/plan-anvil/scripts/execution_contract.py"
    spec = importlib.util.spec_from_file_location("plananvil_execution_contract", path)
    if spec is None or spec.loader is None:
        raise base.QualificationError("unable to load execution_contract.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(
    *, root: Path, runtime_root: Path, schemas: dict[str, Path], version: str,
    os_name: str, source_commit: str, date: str,
) -> tuple[str, bool]:
    cap_id = "C03"
    _, cap_runtime, _, repo, _, results, _ = runtime_paths(root, runtime_root, cap_id)
    base.ensure_git_repo(repo)
    valid = repo / "PLAN.valid.md"
    invalid = repo / "PLAN.invalid.md"
    valid.write_text(_contract_text(valid=True), encoding="utf-8")
    invalid.write_text(_contract_text(valid=False), encoding="utf-8")
    fixture_commit = base.commit_fixture_baseline(repo)

    contract = _load_execution_contract(root)
    valid_findings = contract.execution_contract_findings(valid.read_text(encoding="utf-8"))
    invalid_findings = contract.execution_contract_findings(invalid.read_text(encoding="utf-8"))
    invalid_kinds = {finding.get("kind") for finding in invalid_findings if isinstance(finding, dict)}
    outer_ok = (
        valid_findings == []
        and "execution-contract-topology-missing" in invalid_kinds
        and "agents.max_depth" not in valid.read_text(encoding="utf-8")
    )

    payload = v2._run_trial(
        capability_id=cap_id,
        trial={
            "name": "consume_flat_direct_child_contract",
            "sandbox": "read-only",
            "prompt": (
                "Read PLAN.valid.md and PLAN.invalid.md with read-only shell commands. "
                "Report PASS only if PLAN.valid.md requires flat direct-child topology and "
                "does not rely on agents.max_depth, while PLAN.invalid.md explicitly does."
            ),
        },
        cwd=repo,
        snapshot_repo=repo,
        schemas=schemas,
        results_dir=results,
        position=1,
    )
    live_ok = payload.get("outcome") == "PASS"
    if not outer_ok:
        result, blocker = "FAILED", "The product execution-contract validator did not enforce the audited flat direct-child assertion."
    elif not live_ok:
        result, blocker = "BLOCKED", "The live read-only C03 contract-consumption probe did not complete successfully."
    else:
        result, blocker = "REPRODUCED", None

    return finish(
        root=root,
        cap_runtime=cap_runtime,
        capability_id=cap_id,
        result=result,
        observations=[
            f"valid_contract_findings={len(valid_findings)}",
            f"invalid_topology_rejected={str('execution-contract-topology-missing' in invalid_kinds).lower()}",
            "valid_contract_agents_max_depth_absent=true",
            f"live_contract_consumption_passed={str(live_ok).lower()}",
        ],
        blocker=blocker,
        summary="C03 qualifies the product execution-contract validator directly and is no longer coupled to the Git bootstrap.",
        trials=[{
            **base.sanitize(payload),
            "outer_contract_validation": {
                "valid_findings": len(valid_findings),
                "invalid_topology_rejected": "execution-contract-topology-missing" in invalid_kinds,
            },
        }],
        fixture_commit=fixture_commit,
        version=version,
        os_name=os_name,
        source_commit=source_commit,
        date=date,
    )
