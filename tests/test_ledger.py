"""
Unit tests for the cryptographic local approval ledger.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from swallo.store.db import apply_migrations, get_connection
from swallo.store.ledger import approve, is_approved, list_approvals, revoke


def test_ledger_approve_and_verify(tmp_path: Path) -> None:
    db_file = tmp_path / "swallo.db"
    conn = get_connection(db_file)
    apply_migrations(conn)

    key = secrets.token_bytes(32)
    pkt_hash = "sha256:8c1f2a112233445566778899aabbccddeeff00112233445566778899aabbccdd"

    # Before approval
    assert not is_approved(conn, key, pkt_hash, "claude_code")

    # Approve
    mac = approve(conn, key, pkt_hash, "claude_code")
    assert isinstance(mac, str) and len(mac) == 64

    # Now approved for claude_code
    assert is_approved(conn, key, pkt_hash, "claude_code")

    # Target segregation: not approved for cursor or other targets
    assert not is_approved(conn, key, pkt_hash, "cursor")
    assert not is_approved(conn, key, pkt_hash, "antigravity")


def test_ledger_edit_invalidates_approval(tmp_path: Path) -> None:
    db_file = tmp_path / "swallo.db"
    conn = get_connection(db_file)
    apply_migrations(conn)

    key = secrets.token_bytes(32)
    original_hash = "sha256:1111111111111111111111111111111111111111111111111111111111111111"
    edited_hash = "sha256:2222222222222222222222222222222222222222222222222222222222222222"

    approve(conn, key, original_hash, "claude_code")
    assert is_approved(conn, key, original_hash, "claude_code")

    # Edited hash is NOT approved
    assert not is_approved(conn, key, edited_hash, "claude_code")


def test_ledger_forged_mac_rejected(tmp_path: Path) -> None:
    db_file = tmp_path / "swallo.db"
    conn = get_connection(db_file)
    apply_migrations(conn)

    key = secrets.token_bytes(32)
    pkt_hash = "sha256:3333333333333333333333333333333333333333333333333333333333333333"

    # Attacker inserts a fake row claiming approval with a forged MAC
    conn.execute(
        """
        INSERT INTO approvals (packet_hash, target, approved_at, mac)
        VALUES (?, ?, '2026-10-31T10:00:00Z', 'forged_fake_mac_1234567890')
        """,
        (pkt_hash, "claude_code"),
    )

    # Must be rejected because MAC fails verification
    assert not is_approved(conn, key, pkt_hash, "claude_code")


def test_ledger_revocation(tmp_path: Path) -> None:
    db_file = tmp_path / "swallo.db"
    conn = get_connection(db_file)
    apply_migrations(conn)

    key = secrets.token_bytes(32)
    pkt_hash = "sha256:4444444444444444444444444444444444444444444444444444444444444444"

    approve(conn, key, pkt_hash, "cursor")
    assert is_approved(conn, key, pkt_hash, "cursor")

    # Revoke
    assert revoke(conn, key, pkt_hash, "cursor")
    assert not is_approved(conn, key, pkt_hash, "cursor")

    # Second revoke returns False (nothing to delete)
    assert not revoke(conn, key, pkt_hash, "cursor")


def test_ledger_list_approvals_with_validity(tmp_path: Path) -> None:
    db_file = tmp_path / "swallo.db"
    conn = get_connection(db_file)
    apply_migrations(conn)

    key = secrets.token_bytes(32)
    h1 = "sha256:5555555555555555555555555555555555555555555555555555555555555555"
    h2 = "sha256:6666666666666666666666666666666666666666666666666666666666666666"

    approve(conn, key, h1, "target1")
    conn.execute(
        "INSERT INTO approvals (packet_hash, target, approved_at, mac) VALUES (?, ?, ?, ?)",
        (h2, "target2", "2026-10-31T00:00:00Z", "tampered_mac"),
    )

    items = list_approvals(conn, key)
    assert len(items) == 2
    valid_map = {item["packet_hash"]: item["valid"] for item in items}
    assert valid_map[h1] is True
    assert valid_map[h2] is False
