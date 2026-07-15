from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from common import PlanAnvilError, atomic_write_json, load_json
from scaffold_transaction import JOURNAL_SCHEMA, begin_scaffold_transaction
from schema_validator import validate_file


class ScaffoldJournalTests(unittest.TestCase):
    def _identity(self) -> dict[str, str]:
        return {
            "plan_id": "PG-20260101-000000-ABCD",
            "run_id": "run",
            "base_sha": "0" * 40,
            "planning_branch": "pursue/plan/PG-20260101-000000-ABCD/run",
            "goal_hash": "sha256:" + "1" * 64,
        }

    def test_valid_journal_passes_schema_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            final_root = Path(directory) / "runs/run"
            transaction = begin_scaffold_transaction(final_root, self._identity())
            self.assertIsNotNone(transaction)
            assert transaction is not None

            self.assertEqual(validate_file(transaction.journal_path, JOURNAL_SCHEMA), [])
            journal = load_json(transaction.journal_path)
            self.assertEqual(journal["phase"], "PREPARED")
            self.assertEqual(journal["operation"], "SCAFFOLD_RUN")

    def test_unknown_phase_blocks_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            final_root = Path(directory) / "runs/run"
            identity = self._identity()
            transaction = begin_scaffold_transaction(final_root, identity)
            self.assertIsNotNone(transaction)
            assert transaction is not None
            journal = load_json(transaction.journal_path)
            journal["phase"] = "UNKNOWN"
            atomic_write_json(transaction.journal_path, journal)

            with self.assertRaises(PlanAnvilError) as raised:
                begin_scaffold_transaction(final_root, identity)

            self.assertEqual(raised.exception.code, "SCAFFOLD_JOURNAL_INVALID")
            self.assertTrue(raised.exception.details)

    def test_missing_identity_blocks_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            final_root = Path(directory) / "runs/run"
            identity = self._identity()
            transaction = begin_scaffold_transaction(final_root, identity)
            self.assertIsNotNone(transaction)
            assert transaction is not None
            journal = load_json(transaction.journal_path)
            del journal["identity"]
            atomic_write_json(transaction.journal_path, journal)

            with self.assertRaises(PlanAnvilError) as raised:
                begin_scaffold_transaction(final_root, identity)

            self.assertEqual(raised.exception.code, "SCAFFOLD_JOURNAL_INVALID")
            self.assertTrue(raised.exception.details)


if __name__ == "__main__":
    unittest.main()
