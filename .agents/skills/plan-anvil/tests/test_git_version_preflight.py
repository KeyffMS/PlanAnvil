from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from preflight import _inspect_git_version, parse_git_version, preflight


class GitVersionPreflightTests(unittest.TestCase):
    def _completed(
        self,
        stdout: str,
        *,
        returncode: int = 0,
        stderr: str = "",
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            ["git", "--version"],
            returncode,
            stdout,
            stderr,
        )

    def test_parser_accepts_common_git_version_formats(self) -> None:
        self.assertEqual(parse_git_version("git version 2.30"), (2, 30, 0))
        self.assertEqual(parse_git_version("git version 2.45.1.windows.1"), (2, 45, 1))
        self.assertEqual(parse_git_version("git version 3.0.0"), (3, 0, 0))

    def test_git_2_29_is_rejected(self) -> None:
        with patch(
            "preflight.subprocess.run",
            return_value=self._completed("git version 2.29.9\n"),
        ):
            result = _inspect_git_version()

        self.assertFalse(result["ok"])
        self.assertEqual(result["detected"], "2.29.9")
        self.assertEqual(result["minimum"], "2.30.0")

    def test_git_2_30_is_accepted(self) -> None:
        with patch(
            "preflight.subprocess.run",
            return_value=self._completed("git version 2.30.0\n"),
        ):
            result = _inspect_git_version()

        self.assertTrue(result["ok"])
        self.assertEqual(result["detected"], "2.30.0")

    def test_git_3_is_accepted(self) -> None:
        with patch(
            "preflight.subprocess.run",
            return_value=self._completed("git version 3.0.0\n"),
        ):
            result = _inspect_git_version()

        self.assertTrue(result["ok"])
        self.assertEqual(result["detected"], "3.0.0")

    def test_unparseable_version_is_rejected_fail_closed(self) -> None:
        with patch(
            "preflight.subprocess.run",
            return_value=self._completed("vendor build unknown\n"),
        ):
            result = _inspect_git_version()

        self.assertFalse(result["ok"])
        self.assertIsNone(result["detected"])
        self.assertIn("Could not parse", result["diagnostic"])

    def test_preflight_returns_runtime_blocker_before_repository_access(self) -> None:
        version = {
            "ok": False,
            "detected": "2.29.9",
            "minimum": "2.30.0",
            "diagnostic": "Git 2.29.9 is below the required minimum 2.30.0.",
        }
        with patch("preflight.shutil.which", return_value="/usr/bin/git"), patch(
            "preflight._inspect_git_version", return_value=version
        ), patch("preflight.discover_repo") as discover:
            result = preflight(Path("."))

        discover.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertEqual(result["result"], "GIT_UNAVAILABLE")
        self.assertEqual(result["plan_status"], "BLOCKED_BY_RUNTIME_PREREQUISITE")
        self.assertEqual(result["git_version"], "2.29.9")
        self.assertEqual(result["minimum_git_version"], "2.30.0")


if __name__ == "__main__":
    unittest.main()
