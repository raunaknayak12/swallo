"""
SQLite database connection, transactions, and migration runner for swallo.

Per ADR-008, ADR-026, TRD.md section 5.1 and IMPLEMENTATION_PLAN.md Step 2:
- isolation_level=None with explicit BEGIN IMMEDIATE for writers.
- WAL journal mode, busy_timeout, foreign_keys=ON.
- Schema versioned with PRAGMA user_version.
- 32-byte local key generation with 0600 permissions.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from swallo.errors import IntegrityError

SCHEMA_VERSION = 1

MIGRATION_001_SQL = """
CREATE TABLE IF NOT EXISTS packets (
  id TEXT PRIMARY KEY,
  hash TEXT UNIQUE NOT NULL,
  schema_version TEXT NOT NULL,
  project TEXT NOT NULL,
  parent TEXT,
  created_at TEXT NOT NULL,
  body BLOB NOT NULL,
  origin TEXT NOT NULL,
  expires_at TEXT
);

CREATE TABLE IF NOT EXISTS objects (
  hash TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  size INTEGER NOT NULL,
  redacted INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
  packet_hash TEXT NOT NULL,
  target TEXT NOT NULL,
  approved_at TEXT NOT NULL,
  mac TEXT NOT NULL,
  PRIMARY KEY (packet_hash, target)
);

CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  type TEXT NOT NULL,
  packet_hash TEXT,
  target TEXT,
  detail TEXT,
  prev_mac TEXT NOT NULL,
  mac TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
  root_path TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  registered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rate_state (
  session_id TEXT PRIMARY KEY,
  tokens REAL NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS breaker (
  session_id TEXT PRIMARY KEY,
  blocked_count INTEGER NOT NULL,
  window_start TEXT NOT NULL,
  tripped_until TEXT
);

CREATE TABLE IF NOT EXISTS stale_acks (
  packet_hash TEXT NOT NULL,
  head TEXT NOT NULL,
  drift_hash TEXT NOT NULL,
  acked_at TEXT NOT NULL,
  mac TEXT NOT NULL,
  PRIMARY KEY (packet_hash, head, drift_hash)
);
"""


def get_connection(db_path: Path | str, busy_timeout_ms: int = 5000) -> sqlite3.Connection:
    """
    Open a SQLite connection configured for swallo storage.

    Uses autocommit mode (isolation_level=None) to enforce explicit BEGIN IMMEDIATE transactions.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        str(path),
        isolation_level=None,
        timeout=busy_timeout_ms / 1000.0,
    )
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    timeout_val = int(busy_timeout_ms)
    pragma_sql = f"PRAGMA busy_timeout={timeout_val}"
    conn.executescript(pragma_sql)
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Cursor]:
    """
    Explicit BEGIN IMMEDIATE transaction context manager for writer operations.

    Ensures single-writer concurrency control in SQLite WAL mode.
    """
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    try:
        yield cursor
        cursor.execute("COMMIT")
    except Exception:
        cursor.execute("ROLLBACK")
        raise
    finally:
        cursor.close()


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Retrieve current PRAGMA user_version."""
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA user_version")
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    finally:
        cursor.close()


def apply_migrations(conn: sqlite3.Connection) -> int:
    """
    Apply pending database migrations within an explicit transaction.

    Returns the new schema version.
    """
    current_ver = get_schema_version(conn)
    if current_ver >= SCHEMA_VERSION:
        return current_ver

    if current_ver < 1:
        with transaction(conn) as cur:
            for statement in MIGRATION_001_SQL.strip().split(";"):
                stmt = statement.strip()
                if stmt:
                    cur.execute(stmt)
            cur.execute("PRAGMA user_version = 1")

    return SCHEMA_VERSION


def get_or_create_local_key(key_path: Path | str) -> bytes:
    """
    Retrieve or generate 32 random bytes for local HMAC and keying.

    File is created with 0600 permissions where supported.
    """
    path = Path(key_path)
    if path.is_file():
        key = path.read_bytes()
        if len(key) != 32:
            raise IntegrityError(f"Corrupted local key file at '{path}': expected 32 bytes")
        return key

    path.parent.mkdir(parents=True, exist_ok=True)
    new_key = secrets.token_bytes(32)

    # Use atomic O_CREAT | O_EXCL to prevent race conditions
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY

    mode = 0o600
    fd = os.open(str(path), flags, mode)
    try:
        with open(fd, "wb", closefd=False) as f:
            f.write(new_key)
            f.flush()
            os.fsync(fd)
    finally:
        os.close(fd)

    return new_key
