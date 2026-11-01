"""
Project root registry for swallo.

Per ADR-020, TRD.md section 8, and IMPLEMENTATION_PLAN.md Steps 2 and 7:
- swallo operates strictly on explicitly registered project roots.
- Both the CLI and MCP server refuse requests against unregistered directories.
- Prevents rogue data writes or reading outside approved workspace roots.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from swallo.errors import ValidationError
from swallo.store.db import transaction


def register_project(
    conn: sqlite3.Connection,
    root_path: Path | str,
    name: str | None = None,
    ts: str | None = None,
) -> dict[str, str]:
    """
    Register a workspace root directory in the project registry.

    Args:
        conn: SQLite connection with swallo schema applied.
        root_path: Filesystem path to the project root directory.
        name: Optional human-friendly project name (defaults to directory name).
        ts: Optional ISO timestamp override.

    Returns:
        Dictionary with registered project details.
    """
    path_obj = Path(root_path).resolve()
    if not path_obj.exists():
        raise ValidationError(f"Cannot register nonexistent directory: {path_obj}")
    if not path_obj.is_dir():
        raise ValidationError(f"Project root must be a directory: {path_obj}")

    canonical_root = str(path_obj)
    proj_name = name or path_obj.name or "project"
    if ts is None:
        ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    with transaction(conn) as cur:
        cur.execute(
            """
            INSERT OR REPLACE INTO projects (root_path, name, registered_at)
            VALUES (?, ?, ?)
            """,
            (canonical_root, proj_name, ts),
        )

    return {
        "root_path": canonical_root,
        "name": proj_name,
        "registered_at": ts,
    }


def get_project(conn: sqlite3.Connection, root_path: Path | str) -> dict[str, str] | None:
    """Retrieve details for a registered root path, or None if not found."""
    canonical = str(Path(root_path).resolve())
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT root_path, name, registered_at FROM projects WHERE root_path = ?",
            (canonical,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {"root_path": row[0], "name": row[1], "registered_at": row[2]}
    finally:
        cursor.close()


def is_root_registered(conn: sqlite3.Connection, root_path: Path | str) -> bool:
    """Check if the given exact directory path is registered as a project root."""
    return get_project(conn, root_path) is not None


def list_projects(conn: sqlite3.Connection) -> list[dict[str, str]]:
    """List all registered projects ordered by registration timestamp descending."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT root_path, name, registered_at FROM projects ORDER BY registered_at DESC"
        )
        rows = cursor.fetchall()
        return [{"root_path": r[0], "name": r[1], "registered_at": r[2]} for r in rows]
    finally:
        cursor.close()


def unregister_project(conn: sqlite3.Connection, root_path: Path | str) -> bool:
    """Unregister a project root path. Returns True if a record was removed."""
    canonical = str(Path(root_path).resolve())
    with transaction(conn) as cur:
        cur.execute("DELETE FROM projects WHERE root_path = ?", (canonical,))
        return cur.rowcount > 0


def find_registered_root_for_path(
    conn: sqlite3.Connection,
    target_path: Path | str,
) -> Path | None:
    """
    Find which registered project root contains target_path.

    Returns the matching root Path, or None if target_path does not belong
    to any registered project root.
    """
    target = Path(target_path).resolve()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT root_path FROM projects")
        rows = cursor.fetchall()
    finally:
        cursor.close()

    for (root_str,) in rows:
        root = Path(root_str)
        try:
            target.relative_to(root)
            return root
        except ValueError:
            continue

    return None
