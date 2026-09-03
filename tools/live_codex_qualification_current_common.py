from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import live_codex_qualification as base
import live_codex_qualification_harness_v2 as v2


def finish(
    *, root: Path, cap_runtime: Path, capability_id: str, result: str,
    observations: list[str], blocker: str | None, summary: str,
    trials: list[dict[str, Any]], fixture_commit: str | None,
    version: str, os_name: str, source_commit: str, date: str,
) -> tuple[str, bool]:
    required = base.write_evidence(
        root=root,
        capability_id=capability_id,
        result=result,
        expected_met=result == "REPRODUCED",
        observations=observations,
        blocker=blocker,
        summary=summary,
        trials=[base.sanitize(trial) for trial in trials],
        fixture_commit=fixture_commit,
        version=version,
        os_name=os_name,
        source_commit=source_commit,
        date=date,
    )
    base.local_commit(root, capability_id)
    shutil.rmtree(cap_runtime, ignore_errors=True)
    return result, required


def runtime_paths(root: Path, runtime_root: Path, capability_id: str):
    return v2._runtime_paths(root=root, runtime_root=runtime_root, capability_id=capability_id)
