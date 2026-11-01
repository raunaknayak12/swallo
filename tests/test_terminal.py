"""
Unit tests for controlling terminal detection and confirmation.
"""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest

from swallo.errors import UsageError
from swallo.terminal import confirm_on_terminal, is_terminal_available


def test_confirm_with_injected_stream_yes() -> None:
    sin = io.StringIO("y\n")
    sout = io.StringIO()
    assert confirm_on_terminal("Approve packet?", default=False, stream_in=sin, stream_out=sout)
    assert "Approve packet? [y/N]:" in sout.getvalue()


def test_confirm_with_injected_stream_no() -> None:
    sin = io.StringIO("n\n")
    sout = io.StringIO()
    assert not confirm_on_terminal("Approve packet?", default=True, stream_in=sin, stream_out=sout)
    assert "[Y/n]:" in sout.getvalue()


def test_confirm_with_empty_input_uses_default() -> None:
    sin_default_true = io.StringIO("\n")
    sout = io.StringIO()
    assert confirm_on_terminal(
        "Continue?", default=True, stream_in=sin_default_true, stream_out=sout
    )

    sin_default_false = io.StringIO("\n")
    assert not confirm_on_terminal(
        "Continue?", default=False, stream_in=sin_default_false, stream_out=sout
    )


def test_confirm_non_interactive_raises_usage_error() -> None:
    # When open(CONIN$) / open(/dev/tty) raises OSError and stdin.isatty is False
    with (
        patch("builtins.open", side_effect=OSError("No TTY")),
        patch("sys.stdin.isatty", return_value=False),
        patch("sys.stdout.isatty", return_value=False),
    ):
        with pytest.raises(UsageError, match="controlling terminal is not available"):
            confirm_on_terminal("Approve?")


def test_is_terminal_available_fallback() -> None:
    with (
        patch("builtins.open", side_effect=OSError("No TTY")),
        patch("sys.stdin.isatty", return_value=True),
    ):
        assert is_terminal_available()

    with (
        patch("builtins.open", side_effect=OSError("No TTY")),
        patch("sys.stdin.isatty", return_value=False),
    ):
        assert not is_terminal_available()
