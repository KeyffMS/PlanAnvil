from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common import PlanAnvilError, atomic_write_json, load_json, utc_now


@dataclass
class ScaffoldTransaction:
    final_root: Path
    staging_root: Path
    journal_path: Path
    identity: dict[str, Any]

    @property
    def build_root(self) -> Path:
        return self.staging_root

    def mark(self, phase: str) -> None:
        atomic_write_json(
            self.journal_path,
            {
                "schema_version": "1.1.0",
                "operation": "SCAFFOLD_RUN",
                "phase": phase,
                "updated_at": utc_now(),
                "identity": self.identity,
                "staging_name": self.staging_root.name,
                "final_name": self.final_root.name,
            },
        )

    def publish(self) -> None:
        if self.final_root.exists():
            raise PlanAnvilError(
                f"Run appeared while scaffold transaction was active: {self.final_root}",
                code="RUN_PUBLISH_CONFLICT",
            )
        self.mark("READY_TO_PUBLISH")
        os.replace(self.staging_root, self.final_root)
        _fsync_directory(self.final_root.parent)
        self.mark("PUBLISHED")
        self.journal_path.unlink(missing_ok=True)
        _fsync_directory(self.final_root.parent)


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except (AttributeError, OSError):
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _identity_matches(manifest: dict[str, Any], identity: dict[str, Any]) -> bool:
    repository = manifest.get("repository") if isinstance(manifest, dict) else None
    return (
        manifest.get("plan_id") == identity.get("plan_id")
        and manifest.get("run_id") == identity.get("run_id")
        and isinstance(repository, dict)
        and repository.get("base_sha") == identity.get("base_sha")
        and repository.get("planning_branch") == identity.get("planning_branch")
    )


def existing_scaffold_is_complete(final_root: Path, identity: dict[str, Any]) -> bool:
    required = [
        "manifest.json",
        "state.json",
        "compliance.json",
        "traceability.json",
        "local-state.json",
        "PLAN.md",
        "evidence/original-goal.md",
        "evidence/git-capability.json",
        "evidence/lifecycle.json",
    ]
    if not final_root.is_dir() or any(not (final_root / relative).is_file() for relative in required):
        return False
    try:
        manifest = load_json(final_root / "manifest.json")
    except PlanAnvilError:
        return False
    return isinstance(manifest, dict) and _identity_matches(manifest, identity)


def begin_scaffold_transaction(final_root: Path, identity: dict[str, Any]) -> ScaffoldTransaction | None:
    parent = final_root.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging_root = parent / f".plananvil-scaffold-{final_root.name}"
    journal_path = parent / f".plananvil-scaffold-{final_root.name}.json"

    if final_root.exists():
        if existing_scaffold_is_complete(final_root, identity):
            journal_path.unlink(missing_ok=True)
            if staging_root.exists():
                shutil.rmtree(staging_root)
            return None
        raise PlanAnvilError(
            f"Existing run is incomplete or belongs to another identity: {final_root}",
            code="RUN_INCOMPLETE_OR_MISMATCHED",
        )

    if journal_path.exists():
        try:
            journal = load_json(journal_path)
        except PlanAnvilError as exc:
            raise PlanAnvilError(
                f"Scaffold journal cannot be verified: {journal_path}",
                code="SCAFFOLD_JOURNAL_INVALID",
            ) from exc
        if not isinstance(journal, dict) or journal.get("identity") != identity:
            raise PlanAnvilError(
                f"Scaffold journal belongs to another run: {journal_path}",
                code="SCAFFOLD_JOURNAL_MISMATCH",
            )
    if staging_root.exists():
        shutil.rmtree(staging_root)
    staging_root.mkdir(parents=True)

    transaction = ScaffoldTransaction(final_root, staging_root, journal_path, identity)
    transaction.mark("PREPARED")
    return transaction
