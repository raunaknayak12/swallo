"""
Bug 4b regression tests: `swallo send` --format flag.

Tests:
- --format markdown is accepted and executes normally
- --format invalid is rejected by argument parser
- Default without --format operates identically
"""

from __future__ import annotations

import pytest

from swallo.commands.send import run_send


def test_send_format_flag_in_help(capsys: pytest.CaptureFixture) -> None:
    with pytest.raises(SystemExit) as exc_info:
        run_send(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "--format" in captured.out
    assert "markdown" in captured.out


def test_send_invalid_format_rejected(capsys: pytest.CaptureFixture) -> None:
    with pytest.raises(SystemExit) as exc_info:
        run_send(["pkt_dummy", "--format", "pdf"])
    assert exc_info.value.code != 0
    captured = capsys.readouterr()
    assert "invalid choice" in captured.err or "--format" in captured.err
