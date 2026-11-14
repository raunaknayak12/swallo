"""
Bug 5 regression tests: `swallo staleness` SQLite BLOB decoding.

Verifies:
- _lookup_packet in staleness.py correctly handles bytes/memoryview BLOB values
- Previously, row[2] was coerced via str(row[2]), producing "b'{...}'" which caused
  parse_canonical_json to fail with JSONDecodeError.
- run_staleness succeeds when body is stored as raw BLOB bytes in sqlite3.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from swallo.commands.staleness import _lookup_packet, run_staleness
from swallo.schema.canonical import canonicalize, derive_packet_id, packet_hash
from swallo.store.db import apply_migrations, get_connection


def _insert_blob_packet(store_dir: Path, project: str = "test-proj") -> str:
    db_path = store_dir / "swallo.db"
    conn = get_connection(db_path)
    apply_migrations(conn)
    cur = conn.cursor()

    body_dict = {
        "schema_version": "0.1",
        "project": project,
        "created_at": "2026-11-14T00:00:00Z",
        "sources": [{
            "session_id": "s1",
            "agent": "test",
            "capture_method": "manual",
            "captured_at": "2026-11-14T00:00:00Z",
        }],
        "goal": {"text": "A test packet goal for staleness"},
        "items": [
            {"kind": "decision", "text": "Decision 1"},
        ],
    }

    pkt_h = packet_hash(body_dict)
    pkt_id = derive_packet_id(pkt_h)
    body_bytes = canonicalize(body_dict)

    # Insert body explicitly as raw bytes/BLOB
    cur.execute(
        """
        INSERT INTO packets (id, hash, schema_version, project, created_at, body, origin)
        VALUES (?, ?, '0.1', ?, datetime('now'), ?, 'local')
        """,
        (pkt_id, pkt_h, project, sqlite3.Binary(body_bytes)),
    )
    conn.commit()
    conn.close()
    return pkt_id


def test_staleness_lookup_packet_blob(tmp_path: Path) -> None:
    pkt_id = _insert_blob_packet(tmp_path)
    db_path = tmp_path / "swallo.db"
    conn = get_connection(db_path)

    res = _lookup_packet(conn, pkt_id)
    assert res is not None
    returned_id, returned_hash, returned_body = res
    assert returned_id == pkt_id
    assert not returned_body.startswith("b'")
    assert returned_body.startswith("{")
    assert "A test packet goal for staleness" in returned_body
    conn.close()


def test_run_staleness_with_blob_packet(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pkt_id = _insert_blob_packet(tmp_path)

    # run_staleness should parse the packet cleanly and output packet information
    code = run_staleness([pkt_id, "--store", str(tmp_path)])
    assert code == 0
    captured = capsys.readouterr()
    assert pkt_id in captured.out
    assert "Packet:" in captured.out
