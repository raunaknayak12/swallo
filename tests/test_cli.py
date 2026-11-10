"""
Unit and integration tests for swallo CLI.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from swallo import __version__
from swallo.cli import main


def test_cli_version_text(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["version"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert f"swallo {__version__}" in captured.out
    assert "supported schema versions: 0.1" in captured.out


def test_cli_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--version"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert f"swallo {__version__}" in captured.out


def test_cli_version_json(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["version", "--json"])
    assert exit_code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["version"] == __version__
    assert data["supported_schema_versions"] == ["0.1"]
    assert "python_version" in data


def test_cli_unknown_command_with_suggestions(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["verison"])  # intentional typo
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "Unknown command: 'verison'." in captured.err
    assert "version" in captured.err


def test_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["help"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Available commands:" in captured.out
    assert "version" in captured.out
    assert "init" in captured.out


def test_cli_subprocess_invocation() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "swallo", "version", "--json"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["version"] == __version__


def test_core_import_isolation_and_no_warnings() -> None:
    """Assert import swallo never loads optional extras and emits zero warnings."""
    cmd = [
        sys.executable,
        "-W",
        "error",
        "-c",
        (
            "import swallo\n"
            "import sys\n"
            "assert 'mcp' not in sys.modules, 'mcp leaked into core runtime'\n"
            "assert 'cryptography' not in sys.modules, 'cryptography leaked into core runtime'\n"
            "assert 'tiktoken' not in sys.modules, 'tiktoken leaked into core runtime'\n"
        ),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30)  # noqa: S603
    assert proc.returncode == 0, f"Import isolation check failed: {proc.stderr}"
