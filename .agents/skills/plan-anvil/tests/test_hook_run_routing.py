from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
HOOKS = ROOT / ".codex/hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from plan_anvil_hooklib import (
    ActiveRun,
    active_run_for_event,
    event_has_ambiguous_active_runs,
)


class HookRunRoutingTests(unittest.TestCase):
    def _active(self, planning: Path, source: Path, name: str) -> ActiveRun:
        run_root = planning / ".pursue/runs" / name
        run_root.mkdir(parents=True)
        (run_root / "local-state.json").write_text(
            json.dumps({"paths": {"source_worktree": str(source)}}),
            encoding="utf-8",
        )
        return ActiveRun(planning, run_root, {"mode": "PLAN_GENERATION"})

    def test_source_worktree_resolves_single_linked_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            planning = root / "planning"
            source.mkdir()
            planning.mkdir()
            active = self._active(planning, source, "run-a")
            with patch("plan_anvil_hooklib.git_root", return_value=source), patch(
                "plan_anvil_hooklib.active_runs", return_value=[active]
            ):
                self.assertEqual(active_run_for_event({"cwd": str(source)}), active)

    def test_source_worktree_requires_explicit_id_for_multiple_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            first = self._active(root / "planning-a", source, "run-a")
            second = self._active(root / "planning-b", source, "run-b")
            with patch("plan_anvil_hooklib.git_root", return_value=source), patch(
                "plan_anvil_hooklib.active_runs", return_value=[first, second]
            ):
                event = {"cwd": str(source)}
                self.assertTrue(event_has_ambiguous_active_runs(event))
                self.assertIsNone(active_run_for_event(event))
                selected = active_run_for_event({**event, "plananvil_run_id": "run-b"})
            self.assertEqual(selected, second)


if __name__ == "__main__":
    unittest.main()
