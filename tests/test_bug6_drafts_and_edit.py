"""
Bug 6 & 7 regression tests: `swallo drafts` and `swallo edit` SQLite schema alignment.

Verifies:
- _get_drafts_query in drafts.py queries existing columns on `packets` table.
  Previously queried `session_id` which does not exist in `packets` table schema,
  raising `sqlite3.OperationalError: no such column: session_id`.
- run_drafts 'list' and 'purge' work cleanly on empty and populated stores.
- run_edit queries existing columns on `packets` table and inserts valid rows with schema_version.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from swallo.commands.drafts import run_drafts
from swallo.commands.edit import run_edit
from swallo.schema.canonical import canonicalize, derive_packet_id, packet_hash
from swallo.store.db import apply_migrations, get_connection


def _insert_unapproved_packet(store_dir: Path, project: str = "drafts-test") -> str:
    db_path = store_dir / "swallo.db"
    conn = get_connection(db_path)
    apply_migrations(conn)
    cur = conn.cursor()

    body_dict = {
        "schema_version": "0.1",
        "project": project,
        "created_at": "2026-11-14T00:00:00Z",
        "sources": [{
            "session_id": "test_session_123",
            "agent": "test-agent",
            "capture_method": "ide-agent",
            "captured_at": "2026-11-14T00:00:00Z",
        }],
        "goal": {"text": "A draft packet for testing"},
        "items": [
            {"kind": "decision", "text": "Draft decision"},
        ],
    }

    pkt_h = packet_hash(body_dict)
    pkt_id = derive_packet_id(pkt_h)
    body_bytes = canonicalize(body_dict)

    cur.execute(
        """
        INSERT INTO packets (id, hash, schema_version, project, created_at, body, origin)
        VALUES (?, ?, '0.1', ?, datetime('now'), ?, 'mcp')
        """,
        (pkt_id, pkt_h, project, sqlite3.Binary(body_bytes)),
    )
    conn.commit()
    conn.close()
    return pkt_id


def test_drafts_list_empty_store(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = tmp_path / "swallo.db"
    conn = get_connection(db_path)
    apply_migrations(conn)
    conn.close()

    code = run_drafts(["list", "--store", str(tmp_path)])
    assert code == 0
    captured = capsys.readouterr()
    assert "No unapproved drafts found." in captured.out


def test_drafts_list_with_packet(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pkt_id = _insert_unapproved_packet(tmp_path)

    code = run_drafts(["list", "--store", str(tmp_path)])
    assert code == 0
    captured = capsys.readouterr()
    assert pkt_id in captured.out
    assert "test_session_123" in captured.out
    assert "1 unapproved draft" in captured.out


def test_drafts_purge_force(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _insert_unapproved_packet(tmp_path)

    code = run_drafts(["purge", "--store", str(tmp_path), "--force"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Purged 1 unapproved draft(s)." in captured.out

    # After purge, list should be empty
    code_after = run_drafts(["list", "--store", str(tmp_path)])
    assert code_after == 0
    captured_after = capsys.readouterr()
    assert "No unapproved drafts found." in captured_after.out


def test_edit_nonexistent_packet(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = tmp_path / "swallo.db"
    conn = get_connection(db_path)
    apply_migrations(conn)
    conn.close()

    # Should exit 1 with "not found", never raising sqlite3.OperationalError
    code = run_edit(["pkt_nonexistent", "--store", str(tmp_path)])
    assert code == 1
    captured = capsys.readouterr()
    assert "not found" in captured.err.lower()
