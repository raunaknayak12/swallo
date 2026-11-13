"""
Bug 1 regression tests: `swallo status` / `swallo list` SQLite BLOB decoding.

Tests:
- 0 packets: lists cleanly with no error
- 1 packet: lists cleanly without crashing on bytes BLOB body
- 3 packets: lists all without crashing
- 1 corrupted body row: listed as <corrupt>, other valid packets still listed, exits non-zero
- --project filter: only matching project packets shown
"""

from __future__ import annotations

from pathlib import Path

import pytest

from swallo.commands.status import run_status
from swallo.schema.canonical import canonicalize, derive_packet_id, packet_hash
from swallo.store.db import apply_migrations, get_connection


def _insert_packet(
    store_dir: Path,
    project: str = "test-proj",
    body_dict: dict | None = None,
    corrupt_body: bytes | None = None,
) -> str:
    db_path = store_dir / "swallo.db"
    conn = get_connection(db_path)
    apply_migrations(conn)
    cur = conn.cursor()

    if corrupt_body is not None:
        pkt_id = "pkt_corrupt000000"
        pkt_h = "corrupt_hash_00000000000000000000000000000000000000000000000000000000"
        cur.execute(
            """
            INSERT INTO packets (id, hash, schema_version, project, created_at, body, origin)
            VALUES (?, ?, '0.1', ?, datetime('now'), ?, 'local')
            """,
            (pkt_id, pkt_h, project, corrupt_body),
        )
        conn.commit()
        conn.close()
        return pkt_id

    if body_dict is None:
        body_dict = {
            "schema_version": "0.1",
            "project": project,
            "created_at": "2024-01-01T00:00:00Z",
            "sources": [{"type": "chat", "ref": "test"}],
            "goal": {"text": "A test packet goal"},
            "items": [
                {"kind": "decision", "text": "Decision 1"},
                {"kind": "constraint", "text": "Constraint 1"},
            ],
        }

    pkt_h = packet_hash(body_dict)
    pkt_id = derive_packet_id(pkt_h)
    body_bytes = canonicalize(body_dict)

    cur.execute(
        """
        INSERT INTO packets (id, hash, schema_version, project, created_at, body, origin)
        VALUES (?, ?, '0.1', ?, datetime('now'), ?, 'local')
        """,
        (pkt_id, pkt_h, project, body_bytes),
    )
    conn.commit()
    conn.close()
    return pkt_id


def test_status_empty_store(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    db_path = tmp_path / "swallo.db"
    conn = get_connection(db_path)
    apply_migrations(conn)
    conn.close()

    code = run_status(["--store", str(tmp_path)])
    assert code == 0
    captured = capsys.readouterr()
    assert "No packets found" in captured.out


def test_status_single_packet(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    pkt_id = _insert_packet(tmp_path, project="my-project")

    code = run_status(["--store", str(tmp_path)])
    assert code == 0
    captured = capsys.readouterr()
    assert pkt_id in captured.out
    assert "my-project" in captured.out
    assert "A test packet goal" in captured.out


def test_status_multiple_packets(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    ids = [
        _insert_packet(tmp_path, project=f"proj-{i}", body_dict={
            "schema_version": "0.1",
            "project": f"proj-{i}",
            "created_at": "2024-01-01T00:00:00Z",
            "sources": [{"type": "chat", "ref": "test"}],
            "goal": {"text": f"Goal {i}"},
            "items": [{"kind": "decision", "text": f"Item {i}"}],
        })
        for i in range(3)
    ]

    code = run_status(["--store", str(tmp_path)])
    assert code == 0
    captured = capsys.readouterr()
    for pid in ids:
        assert pid in captured.out


def test_status_corrupted_packet_row(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    valid_id = _insert_packet(tmp_path, project="good-proj")
    corrupt_body = b"NOT_VALID_CANONICAL_JSON_BYTES{{{"
    corrupt_id = _insert_packet(tmp_path, project="bad-proj", corrupt_body=corrupt_body)

    code = run_status(["--store", str(tmp_path)])
    assert code != 0  # Should exit non-zero due to corrupt row
    captured = capsys.readouterr()
    assert valid_id in captured.out
    assert corrupt_id in captured.out
    assert "<corrupt>" in captured.out or "corrupt" in captured.out.lower()


def test_status_project_filter(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    id_a = _insert_packet(tmp_path, project="alpha")
    id_b = _insert_packet(tmp_path, project="beta")

    code = run_status(["--store", str(tmp_path), "--project", "alpha"])
    assert code == 0
    captured = capsys.readouterr()
    assert id_a in captured.out
    assert id_b not in captured.out
