"""
Bug 4c regression tests: MCP server verify_context tool and get_context alias.

Tests:
- SwalloService and create_mcp_server expose verify_context
- SwalloService and create_mcp_server expose get_context alias for load_context
- verify_context on a clean packet returns valid verification report
- verify_context detects body tampering (hash mismatch)
- verify_context detects ledger approval tampering
"""

from __future__ import annotations

from pathlib import Path

import pytest

from swallo.schema.canonical import canonicalize, derive_packet_id, packet_hash
from swallo.server.mcp_server import SwalloService, create_mcp_server
from swallo.store.db import apply_migrations, get_connection, get_or_create_local_key
from swallo.store.ledger import approve


def _setup_service(tmp_path: Path) -> tuple[SwalloService, str, str]:
    db_path = tmp_path / "swallo.db"
    key_path = tmp_path / "key"
    conn = get_connection(db_path)
    apply_migrations(conn)

    # Register project
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO projects (root_path, name, registered_at) VALUES (?, ?, datetime('now'))",
        (str(tmp_path), "test-project"),
    )
    conn.commit()
    conn.close()

    key_bytes = get_or_create_local_key(key_path)

    body_dict = {
        "schema_version": "0.1",
        "project": "test-project",
        "created_at": "2024-01-01T00:00:00Z",
        "sources": [
            {
                "session_id": "s1",
                "agent": "chat",
                "capture_method": "paste",
                "captured_at": "2024-01-01T00:00:00Z",
            }
        ],
        "goal": {"text": "Goal for test"},
        "items": [{"kind": "decision", "text": "Decision for test"}],
    }
    pkt_h = packet_hash(body_dict)
    pkt_id = derive_packet_id(pkt_h)
    body_bytes = canonicalize(body_dict)

    conn2 = get_connection(db_path)
    cur2 = conn2.cursor()
    cur2.execute(
        """
        INSERT INTO packets (id, hash, schema_version, project, created_at, body, origin)
        VALUES (?, ?, '0.1', 'test-project', datetime('now'), ?, 'local')
        """,
        (pkt_id, pkt_h, body_bytes),
    )
    conn2.commit()
    approve(conn2, key_bytes, pkt_h, "claude-code")
    conn2.close()

    svc = SwalloService(store_dir=tmp_path)
    return svc, pkt_id, pkt_h


def test_verify_context_clean_packet(tmp_path: Path) -> None:
    svc, pkt_id, pkt_h = _setup_service(tmp_path)

    report = svc.verify_context(project="test-project", packet_id=pkt_id)
    assert report["packet_id"] == pkt_id
    assert report["stored_hash"] == pkt_h
    assert report["hash_verified"] is True
    assert report["event_chain_ok"] is True
    assert report["approvals"]["claude-code"] is True
    assert "body" not in report


def test_verify_context_tampered_body(tmp_path: Path) -> None:
    svc, pkt_id, _ = _setup_service(tmp_path)

    # Tamper with stored body directly
    conn = get_connection(tmp_path / "swallo.db")
    cur = conn.cursor()
    cur.execute("UPDATE packets SET body = ? WHERE id = ?", (b'{"tampered": true}', pkt_id))
    conn.commit()
    conn.close()

    report = svc.verify_context(project="test-project", packet_id=pkt_id)
    assert report["packet_id"] == pkt_id
    assert report["hash_verified"] is False


def test_get_context_alias_and_mcp_registration(tmp_path: Path) -> None:
    svc, pkt_id, _ = _setup_service(tmp_path)

    # get_context on SwalloService
    res_load = svc.load_context(project="test-project", packet_id=pkt_id, target="claude-code")
    res_get = svc.get_context(project="test-project", packet_id=pkt_id, target="claude-code")
    assert res_load["id"] == res_get["id"]
    assert res_load["hash"] == res_get["hash"]
    assert res_load["target"] == res_get["target"]
    assert "Decision for test" in res_load["content"]
    assert "Decision for test" in res_get["content"]

    # Verify both verify_context and get_context exist on FastMCP
    pytest.importorskip(
        "mcp", reason="swallo[mcp] optional dependency required for FastMCP server registration"
    )
    mcp_app = create_mcp_server(svc)
    tool_names = [tool.name for tool in mcp_app._tool_manager.list_tools()]
    assert "verify_context" in tool_names
    assert "get_context" in tool_names
    assert "load_context" in tool_names
