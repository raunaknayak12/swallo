"""
Regression test: Phase 1-A — `swallo approve --force` must NOT exist in the installed wheel.

The `--force` flag bypasses the mandatory human-TTY confirmation for packet approval.
An IDE agent with shell access could call `swallo approve <id> --force` without any
human interaction, violating the security invariant documented in Security.md F21.

This test verifies:
1. The `--force` / `-f` flags are absent from `swallo approve` argument parser.
2. Calling `run_approve` with `--force` raises SystemExit (unrecognised argument).
3. The shipped `confirm_on_terminal` function raises UsageError when no TTY is available.
4. No environment variable, flag, or argument in the installed CLI can approve non-interactively.
"""

from __future__ import annotations

import io as _io
import json as _json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from swallo.commands.approve import run_approve
from swallo.errors import UsageError
from swallo.terminal import confirm_on_terminal


def _init_store_with_packet(tmp_path: Path) -> tuple[str, str]:
    """Create a minimal store and save a packet; return (pkt_id, pkt_hash)."""
    from swallo.cli import main

    main(["init", "--store", str(tmp_path), "--project", "TestProject"])

    packet_data = {
        "schema_version": "0.1",
        "project": "TestProject",
        "created_at": "2026-11-01T00:00:00Z",
        "sources": [
            {
                "session_id": "s1",
                "agent": "test",
                "capture_method": "paste",
                "captured_at": "2026-11-01T00:00:00Z",
            }
        ],
        "goal": {"text": "No-force security test"},
        "items": [{"kind": "decision", "text": "Verify force bypass is gone."}],
    }
    pf = tmp_path / "packet.json"
    pf.write_text(_json.dumps(packet_data), encoding="utf-8")

    out = _io.StringIO()
    with patch("sys.stdout", out):
        rc = main(["save", str(pf), "--store", str(tmp_path), "--json"])
    assert rc == 0, f"save failed: {out.getvalue()}"
    out.seek(0)
    result = _json.loads(out.getvalue())
    return str(result["id"]), str(result["hash"])


def test_approve_force_flag_does_not_exist(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """
    FAILING TEST (Phase 1-A): The --force flag must be absent from the installed wheel.
    If this test passes, the flag has been removed and the fix is complete.
    If this test fails with 'unrecognised arguments: --force', the flag still ships.
    """
    pkt_id, _ = _init_store_with_packet(tmp_path)

    # Calling approve with --force must raise SystemExit (unrecognized argument),
    # NOT proceed to skip the TTY check.
    with pytest.raises(SystemExit) as exc_info:
        run_approve([pkt_id, "--target", "claude-code", "--force", "--store", str(tmp_path)])

    # Exit code 2 = argparse "unrecognized argument" error
    assert exc_info.value.code == 2, (
        f"Expected exit code 2 (unrecognized --force argument), got {exc_info.value.code}. "
        "The --force flag still ships in the installed wheel — this is a production TTY bypass."
    )


def test_approve_force_shortflag_does_not_exist(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """The -f shorthand for --force must also be absent."""
    pkt_id, _ = _init_store_with_packet(tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        run_approve([pkt_id, "--target", "claude-code", "-f", "--store", str(tmp_path)])

    assert exc_info.value.code == 2, (
        f"Expected exit code 2 (unrecognized -f argument), got {exc_info.value.code}. "
        "The -f shorthand for --force still ships in the installed wheel."
    )


def test_no_env_var_bypasses_tty_approval() -> None:
    """
    No environment variable may bypass interactive TTY confirmation.
    confirm_on_terminal must raise UsageError when no TTY is available,
    regardless of any environment variables.
    """
    with (
        patch.dict(os.environ, {"SWALLO_TEST_STUB": "1", "SWALLO_FORCE_APPROVE": "1"}, clear=False),
        patch("builtins.open", side_effect=OSError("No TTY")),
        patch("sys.stdin.isatty", return_value=False),
        patch("sys.stdout.isatty", return_value=False),
    ):
        with pytest.raises(UsageError, match="controlling terminal is not available"):
            confirm_on_terminal("Approve packet?")


def test_non_interactive_approve_requires_tty(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """
    When no TTY is available, `run_approve` must raise UsageError — not silently approve.
    This validates the approve command calls confirm_on_terminal and doesn't bypass it.
    """
    pkt_id, _ = _init_store_with_packet(tmp_path)

    # Simulate a fully headless environment (no TTY available)
    with (
        patch("builtins.open", side_effect=OSError("No TTY")),
        patch("sys.stdin.isatty", return_value=False),
        patch("sys.stdout.isatty", return_value=False),
    ):
        with pytest.raises(UsageError, match="controlling terminal is not available"):
            run_approve([pkt_id, "--target", "claude-code", "--store", str(tmp_path)])
