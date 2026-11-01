"""
Unit tests for the tamper-evident, hash-chained event log.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from swallo.store.db import apply_migrations, get_connection
from swallo.store.eventlog import append, list_events, verify


def test_eventlog_empty_verify(tmp_path: Path) -> None:
    db_file = tmp_path / "swallo.db"
    conn = get_connection(db_file)
    apply_migrations(conn)

    key = secrets.token_bytes(32)
    assert verify(conn, key) == []


def test_eventlog_append_and_verify(tmp_path: Path) -> None:
    db_file = tmp_path / "swallo.db"
    conn = get_connection(db_file)
    apply_migrations(conn)

    key = secrets.token_bytes(32)

    mac1 = append(conn, key, type="packet_saved", packet_hash="sha256:aaa", detail="First packet")
    mac2 = append(
        conn,
        key,
        type="packet_approved",
        packet_hash="sha256:aaa",
        target="claude_code",
        detail="Approved for claude",
    )
    mac3 = append(conn, key, type="packet_delivered", packet_hash="sha256:aaa", detail="Delivered")

    assert mac1 != mac2
    assert mac2 != mac3

    # Clean log should verify without errors
    errors = verify(conn, key)
    assert errors == []

    events = list_events(conn)
    assert len(events) == 3
    assert events[0]["type"] == "packet_delivered"
    assert events[2]["type"] == "packet_saved"


def test_eventlog_tampering_detected(tmp_path: Path) -> None:
    db_file = tmp_path / "swallo.db"
    conn = get_connection(db_file)
    apply_migrations(conn)

    key = secrets.token_bytes(32)

    append(conn, key, type="packet_saved", packet_hash="sha256:111", detail="Good")
    append(conn, key, type="packet_approved", packet_hash="sha256:111", target="claude")

    assert verify(conn, key) == []

    # Attacker tampers with row 1's detail
    conn.execute("UPDATE events SET detail = 'Malicious change' WHERE seq = 1")

    errors = verify(conn, key)
    assert len(errors) > 0
    assert any("HMAC mismatch" in e for e in errors)


def test_eventlog_deleted_row_detected(tmp_path: Path) -> None:
    db_file = tmp_path / "swallo.db"
    conn = get_connection(db_file)
    apply_migrations(conn)

    key = secrets.token_bytes(32)

    append(conn, key, type="event1", detail="1")
    append(conn, key, type="event2", detail="2")
    append(conn, key, type="event3", detail="3")

    assert verify(conn, key) == []

    # Attacker deletes event #2
    conn.execute("DELETE FROM events WHERE seq = 2")

    errors = verify(conn, key)
    assert len(errors) > 0
    assert any("broken chain" in e for e in errors)


def test_eventlog_wrong_key_fails_verification(tmp_path: Path) -> None:
    db_file = tmp_path / "swallo.db"
    conn = get_connection(db_file)
    apply_migrations(conn)

    key = secrets.token_bytes(32)
    wrong_key = secrets.token_bytes(32)

    append(conn, key, type="init", detail="initialized")

    errors = verify(conn, wrong_key)
    assert len(errors) == 1
    assert "HMAC mismatch" in errors[0]

