"""
Bug 3 regression tests: Target name normalization (`claude_code` vs `claude-code`).

Tests:
- approve default (or --target claude_code) records canonical claude-code
- approve with unknown target rejects with clear error listing supported targets
- is_approved() with legacy row stored as target="claude_code" returns True for "claude-code"
- is_approved() with tampered MAC returns False
- show reports supported targets dynamically
"""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
from unittest.mock import patch

import pytest

from swallo.commands.approve import run_approve
from swallo.commands.show import run_show
from swallo.errors import UsageError
from swallo.schema.canonical import canonicalize, derive_packet_id, packet_hash
from swallo.store.db import apply_migrations, get_connection, get_or_create_local_key
from swallo.store.ledger import approve, is_approved


def _setup_store_with_packet(store_dir: Path) -> tuple[str, str, bytes]:
    db_path = store_dir / "swallo.db"
    key_path = store_dir / "key"
    conn = get_connection(db_path)
    apply_migrations(conn)
    key_bytes = get_or_create_local_key(key_path)

    body_dict = {
        "schema_version": "0.1",
        "project": "demo",
        "created_at": "2024-01-01T00:00:00Z",
        "sources": [
            {
                "session_id": "s1",
                "agent": "chat",
                "capture_method": "paste",
                "captured_at": "2024-01-01T00:00:00Z",
            }
        ],
        "goal": {"text": "Goal for bug3 test"},
        "items": [{"kind": "decision", "text": "Decision for bug3"}],
    }
    pkt_h = packet_hash(body_dict)
    pkt_id = derive_packet_id(pkt_h)
    body_bytes = canonicalize(body_dict)

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO packets (id, hash, schema_version, project, created_at, body, origin)
        VALUES (?, ?, '0.1', 'demo', datetime('now'), ?, 'local')
        """,
        (pkt_id, pkt_h, body_bytes),
    )
    conn.commit()
    conn.close()
    return pkt_id, pkt_h, key_bytes


def test_approve_normalizes_target_and_rejects_unknown(tmp_path: Path) -> None:
    pkt_id, pkt_h, key_bytes = _setup_store_with_packet(tmp_path)

    # 1. Unknown target must raise UsageError with supported targets listed
    with pytest.raises(UsageError, match="Supported targets"):
        run_approve([pkt_id, "--target", "nonexistent-target", "--store", str(tmp_path)])

    # 2. Approve with claude_code should normalize to claude-code in ledger
    # Inject a "y" answer so confirm_on_terminal doesn't require a real TTY
    with patch("swallo.commands.approve.confirm_on_terminal", return_value=True):
        ret = run_approve([pkt_id, "--target", "claude_code", "--store", str(tmp_path)])
    assert ret == 0

    conn = get_connection(tmp_path / "swallo.db")
    cur = conn.cursor()
    cur.execute("SELECT target FROM approvals WHERE packet_hash = ?", (pkt_h,))
    rows = cur.fetchall()
    conn.close()

    assert len(rows) == 1
    assert rows[0][0] == "claude-code"


def test_is_approved_backward_compatibility_with_legacy_rows(tmp_path: Path) -> None:
    pkt_id, pkt_h, key_bytes = _setup_store_with_packet(tmp_path)
    conn = get_connection(tmp_path / "swallo.db")

    # Insert a legacy row with target="claude_code" and a valid MAC computed against "claude_code"
    ts = "2024-01-01T12:00:00Z"
    payload = f"approval\0{pkt_h}\0claude_code\0{ts}".encode()
    valid_mac = hmac.new(key_bytes, payload, hashlib.sha256).hexdigest()

    cur = conn.cursor()
    cur.execute(
        "INSERT INTO approvals (packet_hash, target, approved_at, mac) VALUES (?, ?, ?, ?)",
        (pkt_h, "claude_code", ts, valid_mac),
    )
    conn.commit()

    # Reading with canonical target "claude-code" must find and verify this legacy row!
    assert is_approved(conn, key_bytes, pkt_h, "claude-code") is True
    # Reading with legacy name should also verify
    assert is_approved(conn, key_bytes, pkt_h, "claude_code") is True

    # Tampered legacy row should fail verification
    cur.execute(
        "UPDATE approvals SET mac = 'deadbeef00000000' WHERE packet_hash = ?",
        (pkt_h,),
    )
    conn.commit()
    conn.close()

    conn2 = get_connection(tmp_path / "swallo.db")
    assert is_approved(conn2, key_bytes, pkt_h, "claude-code") is False
    conn2.close()


def test_show_lists_supported_targets(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    pkt_id, pkt_h, key_bytes = _setup_store_with_packet(tmp_path)

    # Approve for claude-code
    conn = get_connection(tmp_path / "swallo.db")
    approve(conn, key_bytes, pkt_h, "claude-code")
    conn.close()

    ret = run_show([pkt_id, "--store", str(tmp_path)])
    assert ret == 0
    captured = capsys.readouterr()
    assert "[APPROVED]      claude-code" in captured.out
    assert "antigravity" in captured.out
    assert "cursor" in captured.out


def test_new_approvals_end_to_end_targets(tmp_path: Path) -> None:
    """Verify new approvals work end-to-end for claude-code, cursor, and antigravity."""
    pkt_id, pkt_h, key_bytes = _setup_store_with_packet(tmp_path)
    for target in ["claude-code", "cursor", "antigravity"]:
        with patch("swallo.commands.approve.confirm_on_terminal", return_value=True):
            ret = run_approve([pkt_id, "--target", target, "--store", str(tmp_path)])
        assert ret == 0
        conn = get_connection(tmp_path / "swallo.db")
        assert is_approved(conn, key_bytes, pkt_h, target) is True
        conn.close()
