"""
Unit and concurrency tests for SQLite database, migrations, transactions, and object store.
"""

from __future__ import annotations

import concurrent.futures
from pathlib import Path

import pytest

from swallo.errors import IntegrityError
from swallo.store.db import (
    apply_migrations,
    get_connection,
    get_or_create_local_key,
    get_schema_version,
    transaction,
)
from swallo.store.objects import ObjectStore


def test_sqlite_connection_pragmas(tmp_path: Path) -> None:
    db_file = tmp_path / "swallo.db"
    conn = get_connection(db_file)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode")
        assert cur.fetchone()[0].upper() == "WAL"

        cur.execute("PRAGMA foreign_keys")
        assert cur.fetchone()[0] == 1

        cur.execute("PRAGMA busy_timeout")
        assert cur.fetchone()[0] == 5000
    finally:
        conn.close()


def test_apply_migrations(tmp_path: Path) -> None:
    db_file = tmp_path / "swallo.db"
    conn = get_connection(db_file)
    try:
        assert get_schema_version(conn) == 0

        new_ver = apply_migrations(conn)
        assert new_ver == 1
        assert get_schema_version(conn) == 1

        # Check required tables exist
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cur.fetchall()}
        expected_tables = {
            "packets",
            "objects",
            "approvals",
            "events",
            "meta",
            "projects",
            "rate_state",
            "breaker",
            "stale_acks",
        }
        assert expected_tables.issubset(tables)
    finally:
        conn.close()


def test_explicit_transaction_rollback(tmp_path: Path) -> None:
    db_file = tmp_path / "swallo.db"
    conn = get_connection(db_file)
    try:
        apply_migrations(conn)

        with pytest.raises(RuntimeError, match="Intentional failure"):
            with transaction(conn) as cur:
                cur.execute(
                    "INSERT INTO meta (key, value) VALUES (?, ?)",
                    ("test_key", "test_val"),
                )
                raise RuntimeError("Intentional failure mid-write")

        # Verify rollback left no state
        cur = conn.cursor()
        cur.execute("SELECT value FROM meta WHERE key = ?", ("test_key",))
        assert cur.fetchone() is None
    finally:
        conn.close()


def test_parallel_writers_concurrency(tmp_path: Path) -> None:
    db_file = tmp_path / "swallo.db"
    init_conn = get_connection(db_file)
    apply_migrations(init_conn)
    init_conn.close()

    num_writers = 8
    items_per_writer = 25

    def _worker(worker_id: int) -> int:
        worker_conn = get_connection(db_file, busy_timeout_ms=10000)
        try:
            for i in range(items_per_writer):
                with transaction(worker_conn) as cur:
                    cur.execute(
                        "INSERT INTO meta (key, value) VALUES (?, ?)",
                        (f"k_{worker_id}_{i}", f"val_{worker_id}_{i}"),
                    )
            return items_per_writer
        finally:
            worker_conn.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_writers) as executor:
        futures = [executor.submit(_worker, w) for w in range(num_writers)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert sum(results) == num_writers * items_per_writer

    verify_conn = get_connection(db_file)
    try:
        cur = verify_conn.cursor()
        cur.execute("SELECT count(*) FROM meta WHERE key LIKE 'k_%'")
        count = cur.fetchone()[0]
        assert count == num_writers * items_per_writer
    finally:
        verify_conn.close()


def test_object_store_roundtrip(tmp_path: Path) -> None:
    store = ObjectStore(tmp_path)
    data = b"Transcript content with special chars: \xc3\xa9\xc3\xa0\xc3\xb4"

    hash_ = store.put(data)
    assert hash_.startswith("sha256:")
    assert store.exists(hash_) is True

    retrieved = store.get(hash_)
    assert retrieved == data

    # Verify sharded filesystem structure
    raw_hex = hash_.removeprefix("sha256:")
    shard = raw_hex[:2]
    rest = raw_hex[2:]
    expected_file = tmp_path / "objects" / shard / rest
    assert expected_file.is_file()


def test_object_store_missing(tmp_path: Path) -> None:
    store = ObjectStore(tmp_path)
    fake_hash = "sha256:" + "0" * 64
    assert store.exists(fake_hash) is False
    with pytest.raises(FileNotFoundError):
        store.get(fake_hash)


def test_local_key_generation(tmp_path: Path) -> None:
    key_file = tmp_path / "keys" / "local.key"
    key1 = get_or_create_local_key(key_file)
    assert len(key1) == 32

    # Second call returns the same key
    key2 = get_or_create_local_key(key_file)
    assert key1 == key2

    # Corrupt key file test
    key_file.write_bytes(b"too_short")
    with pytest.raises(IntegrityError, match="Corrupted local key"):
        get_or_create_local_key(key_file)
