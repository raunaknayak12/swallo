"""
Local cryptographic approval ledger for swallo.

Per ADR-003, ADR-007, IMPLEMENTATION_PLAN.md Step 3, and Security.md F2:
- Approval state lives in a local SQLite ledger, NEVER inside the packet file itself.
- Each approval row binds (packet_hash, target, approved_at) with an HMAC-SHA256 MAC
  derived from the local machine key.
- Any edit to a packet changes its hash and invalidates previous approvals.
- Revocation explicitly removes the approval row and logs the revocation in the event log.
"""

from __future__ import annotations

import hashlib
import hmac
import sqlite3
from datetime import UTC, datetime
from typing import Any

from swallo.store.db import transaction
from swallo.store.eventlog import append as log_event


def approve(
    conn: sqlite3.Connection,
    key: bytes,
    packet_hash: str,
    target: str,
    ts: str | None = None,
) -> str:
    """
    Record human approval of a packet hash for a specific IDE target.

    Computes HMAC-SHA256(key, "approval\0" + packet_hash + "\0" + target + "\0" + ts)
    and stores the record in an explicit transaction.
    """
    if ts is None:
        ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    payload = f"approval\0{packet_hash}\0{target}\0{ts}".encode()
    mac = hmac.new(key, payload, hashlib.sha256).hexdigest()

    with transaction(conn) as cur:
        cur.execute(
            """
            INSERT OR REPLACE INTO approvals (packet_hash, target, approved_at, mac)
            VALUES (?, ?, ?, ?)
            """,
            (packet_hash, target, ts, mac),
        )

    # Log to event log
    log_event(
        conn,
        key,
        type="packet_approved",
        packet_hash=packet_hash,
        target=target,
        detail=f"Approved for target {target}",
        ts=ts,
    )

    return mac


def is_approved(
    conn: sqlite3.Connection,
    key: bytes,
    packet_hash: str,
    target: str,
) -> bool:
    """
    Verify whether a packet hash is currently approved for the specified target.

    Supports both canonical hyphenated target names and legacy underscore variants
    without requiring rewriting historical ledger rows. Each row's MAC is verified
    against the exact target string originally recorded.

    Returns True ONLY if a matching row exists and its MAC verifies successfully.
    """
    from swallo.adapters.registry import normalize_target

    canonical = normalize_target(target)
    legacy = canonical.replace("-", "_")
    candidates = [canonical] if canonical == legacy else [canonical, legacy]

    cursor = conn.cursor()
    try:
        # Avoid dynamic query construction: query candidates with fixed parameterized OR clauses
        if len(candidates) == 1:
            cursor.execute(
                """
                SELECT target, approved_at, mac
                FROM approvals
                WHERE packet_hash = ? AND target = ?
                """,
                (packet_hash, candidates[0]),
            )
        else:
            cursor.execute(
                """
                SELECT target, approved_at, mac
                FROM approvals
                WHERE packet_hash = ? AND (target = ? OR target = ?)
                """,
                (packet_hash, candidates[0], candidates[1]),
            )
        rows = cursor.fetchall()
    finally:
        cursor.close()

    if not rows:
        return False

    for stored_target, approved_at, stored_mac in rows:
        payload = f"approval\0{packet_hash}\0{stored_target}\0{approved_at}".encode()
        expected_mac = hmac.new(key, payload, hashlib.sha256).hexdigest()
        if hmac.compare_digest(stored_mac, expected_mac):
            return True

    return False


def revoke(
    conn: sqlite3.Connection,
    key: bytes,
    packet_hash: str,
    target: str,
) -> bool:
    """
    Revoke a previously granted approval.

    Returns True if an approval was found and deleted, False otherwise.
    """
    with transaction(conn) as cur:
        cur.execute(
            """
            DELETE FROM approvals
            WHERE packet_hash = ? AND target = ?
            """,
            (packet_hash, target),
        )
        deleted = cur.rowcount > 0

    if deleted:
        log_event(
            conn,
            key,
            type="packet_revoked",
            packet_hash=packet_hash,
            target=target,
            detail=f"Revoked approval for target {target}",
        )

    return deleted


def list_approvals(conn: sqlite3.Connection, key: bytes) -> list[dict[str, Any]]:
    """
    List all recorded approvals along with their cryptographic verification status.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT packet_hash, target, approved_at, mac
            FROM approvals
            ORDER BY approved_at DESC
            """
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()

    results: list[dict[str, Any]] = []
    for r in rows:
        pkt_hash, target, approved_at, stored_mac = r[0], r[1], r[2], r[3]
        payload = f"approval\0{pkt_hash}\0{target}\0{approved_at}".encode()
        expected_mac = hmac.new(key, payload, hashlib.sha256).hexdigest()
        is_valid = hmac.compare_digest(stored_mac, expected_mac)
        results.append(
            {
                "packet_hash": pkt_hash,
                "target": target,
                "approved_at": approved_at,
                "mac": stored_mac,
                "valid": is_valid,
            }
        )

    return results
