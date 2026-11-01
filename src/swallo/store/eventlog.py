"""
Tamper-evident, hash-chained audit event log for swallo.

Per TRD.md sections 4 and 5.1, IMPLEMENTATION_PLAN.md Step 3, and Security.md F10:
- Every significant action (save, approve, revoke, deliver, breaker) is appended to events.
- Each event row is chained to the previous row's MAC:
    mac_i = HMAC-SHA256(key, prev_mac || canonical(row without mac))
- verify(conn, key) traverses the entire chain to detect any tampering, modification,
  row deletion, or reordering.
"""

from __future__ import annotations

import hashlib
import hmac
import sqlite3
from datetime import UTC, datetime
from typing import Any

from swallo.schema.canonical import canonicalize
from swallo.store.db import transaction

# Genesis MAC representing the initial root of the hash chain
GENESIS_MAC = "0" * 64


def append(
    conn: sqlite3.Connection,
    key: bytes,
    type: str,
    packet_hash: str | None = None,
    target: str | None = None,
    detail: str = "",
    ts: str | None = None,
) -> str:
    """
    Append an event to the tamper-evident log within an explicit transaction.

    Returns the computed MAC of the newly appended event.
    """
    if ts is None:
        ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    with transaction(conn) as cur:
        # Find previous MAC in chain
        cur.execute("SELECT mac FROM events ORDER BY seq DESC LIMIT 1")
        row = cur.fetchone()
        prev_mac = row[0] if row else GENESIS_MAC

        payload: dict[str, object] = {
            "detail": detail,
            "packet_hash": packet_hash,
            "prev_mac": prev_mac,
            "target": target,
            "ts": ts,
            "type": type,
        }
        canonical_bytes = canonicalize(payload)

        # Compute HMAC-SHA256(key, prev_mac || canonical_bytes)
        mac = hmac.new(key, prev_mac.encode("utf-8") + canonical_bytes, hashlib.sha256).hexdigest()

        cur.execute(
            """
            INSERT INTO events (ts, type, packet_hash, target, detail, prev_mac, mac)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (ts, type, packet_hash, target, detail, prev_mac, mac),
        )

    return mac


def verify(conn: sqlite3.Connection, key: bytes) -> list[str]:
    """
    Verify the integrity of the entire event log chain.

    Returns a list of discrepancy descriptions. An empty list indicates
    the entire log is authentic and un-tampered.
    """
    errors: list[str] = []
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT seq, ts, type, packet_hash, target, detail, prev_mac, mac
            FROM events
            ORDER BY seq ASC
            """
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()

    expected_prev = GENESIS_MAC

    for row in rows:
        seq: int = row[0]
        ts: str = row[1]
        type_: str = row[2]
        packet_hash: str | None = row[3]
        target: str | None = row[4]
        detail: str = row[5]
        prev_mac: str = row[6]
        stored_mac: str = row[7]

        # Check chain link continuity
        if prev_mac != expected_prev:
            errors.append(
                f"Event #{seq} ({type_}): broken chain. Expected prev_mac "
                f"'{expected_prev[:12]}...', got '{prev_mac[:12]}...'"
            )

        # Recompute HMAC
        payload: dict[str, object] = {
            "detail": detail,
            "packet_hash": packet_hash,
            "prev_mac": prev_mac,
            "target": target,
            "ts": ts,
            "type": type_,
        }
        canonical_bytes = canonicalize(payload)
        expected_mac = hmac.new(
            key, prev_mac.encode("utf-8") + canonical_bytes, hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(stored_mac, expected_mac):
            errors.append(
                f"Event #{seq} ({type_}): HMAC mismatch. Stored MAC does not match "
                "recalculated MAC (tampering or corrupted key detected)"
            )

        expected_prev = stored_mac

    return errors


def list_events(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    """Retrieve recent event log entries ordered from newest to oldest."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT seq, ts, type, packet_hash, target, detail, prev_mac, mac
            FROM events
            ORDER BY seq DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        return [
            {
                "seq": r[0],
                "ts": r[1],
                "type": r[2],
                "packet_hash": r[3],
                "target": r[4],
                "detail": r[5],
                "prev_mac": r[6],
                "mac": r[7],
            }
            for r in rows
        ]
    finally:
        cursor.close()
