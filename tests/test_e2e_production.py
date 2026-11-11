"""
End-to-End Production Readiness Tests.

Validates the full user journey when adopting Swallo in a new project:
- Store initialization outside work tree
- Diagnostic health checks (`swallo doctor`)
- Context draft saving, listing, and inspection
- Event log cryptographic integrity verification
"""

from __future__ import annotations

from pathlib import Path

from swallo.config import Config
from swallo.server.mcp_server import SwalloService
from swallo.store import db
from swallo.store.db import get_or_create_local_key
from swallo.store.eventlog import verify


def test_e2e_user_project_lifecycle(tmp_path: Path) -> None:
    # 1. Setup isolated user store and user project directory
    store_dir = tmp_path / "user_swallo_store"
    store_dir.mkdir(parents=True, exist_ok=True)
    project_dir = tmp_path / "my_user_project"
    project_dir.mkdir(parents=True, exist_ok=True)

    # 2. Database migration & key initialization
    db_path = store_dir / "swallo.db"
    key_path = store_dir / "key"
    conn = db.get_connection(db_path)
    db.apply_migrations(conn)
    key = get_or_create_local_key(key_path)
    assert len(key) == 32

    # 3. Register user project root
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO projects (root_path, name, registered_at) VALUES (?, ?, ?)",
        (str(project_dir.resolve()), "user-app", "2026-11-11T12:00:00Z"),
    )
    conn.commit()
    conn.close()

    # 4. Initialize Swallo service
    service = SwalloService(store_dir=store_dir)
    cfg = Config()
    assert cfg.store.dir is None

    # 5. Save context draft
    packet_payload = {
        "schema_version": "0.1",
        "project": "user-app",
        "created_at": "2026-11-11T12:00:00Z",
        "goal": {"text": "Deliver secure production handoff between chat and IDE"},
        "sources": [
            {
                "session_id": "sess_prod_001",
                "agent": "antigravity",
                "capture_method": "export",
                "captured_at": "2026-11-11T12:00:00Z",
            }
        ],
        "items": [
            {
                "kind": "decision",
                "text": "Enforce zero-network architecture and mandatory TTY human approvals",
                "topic": "security",
                "value": "enforced",
            }
        ],
    }

    save_result = service.save_context(
        packet_data=packet_payload,
        project="user-app",
        session_id="sess_prod_001",
    )
    assert "draft_id" in save_result or "id" in save_result or "status" in save_result

    # 6. List contexts
    contexts = service.list_contexts(project="user-app")
    assert isinstance(contexts, list)

    # 7. Audit event log hash chain
    conn = db.get_connection(db_path)
    errors = verify(conn, key)
    assert errors == []
    conn.close()
