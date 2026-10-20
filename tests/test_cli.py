"""Tests for the CLI entry point."""

from __future__ import annotations

import subprocess
import sys

from groundskeeper import __version__


class TestModuleEntryPoint:
    def test_runs_as_python_dash_m(self):
        result = subprocess.run(
            [sys.executable, "-m", "groundskeeper", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert __version__ in result.stdout
