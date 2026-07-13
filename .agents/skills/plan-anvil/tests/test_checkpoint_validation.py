from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from _helpers import init_repo
from common import atomic_write_json, sha256_file

ROOT = Path(__file__).resolve().parents[4]
HOOKS = ROOT / ".codex/hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from plan_anvil_checkpoint import validate_checkpoint_for_run
from plan_anvil_hooklib import ActiveRun


class CheckpointValidationTests(unittest.TestCase):
    def test_non_object_checkpoint_returns_failure_without_raising(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = init_repo(Path(directory) / "repo")
            run_root = repo / ".pursue/runs/run"
            checkpoint = run_root / "checkpoints/CHECKPOINT-01-VERIFIED.json"
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_text("[]\n", encoding="utf-8")
            state = {
                "mode": "PLAN_EXECUTION",
                "last_checkpoint": "checkpoints/CHECKPOINT-01-VERIFIED.json",
                "next_action": {"type": "VERIFY", "target": None},
                "artifact_hashes": {
                    "checkpoints/CHECKPOINT-01-VERIFIED.json": sha256_file(checkpoint),
                },
            }
            atomic_write_json(run_root / "state.json", state)
            active = ActiveRun(repo, run_root, state)

            result = validate_checkpoint_for_run(active)

            self.assertFalse(result.ok)
            self.assertIn("checkpoint JSON root is not an object", result.reasons)


if __name__ == "__main__":
    unittest.main()
