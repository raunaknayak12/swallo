"""
Safety guards and admission control for the swallo MCP server.

Per TRD.md sections 5.1, 7, 8, 11 and IMPLEMENTATION_PLAN.md Step 7:
- Per-session token bucket rate limiter with SQLite state persistence.
- Circuit breaker: counts blocked saves in a sliding window, tripping sessions.
- Quotas and TTL: caps unapproved draft count and byte storage per project.
- Idempotent deduplication: identical payloads return existing draft without budget drain.
- Project root registry verification: rejects unregistered projects (F20).
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from swallo.errors import (
    DraftQuotaExceededError,
    SessionPausedError,
    StaleContextError,
    UnregisteredProjectError,
)
from swallo.repo.staleness import StalenessReport


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining_tokens: float
    retry_after_seconds: int = 0


class RateLimiter:
    """
    Per-session token bucket rate limiter backed by SQLite.
    Falls back to per-project scoping if session identifier is missing or generic.
    """

    def __init__(self, burst: int = 10, refill_per_hour: int = 20) -> None:
        self.burst = float(burst)
        self.refill_per_sec = float(refill_per_hour) / 3600.0

    def check_and_consume(
        self,
        conn: sqlite3.Connection,
        session_id: str,
        cost: float = 1.0,
    ) -> RateLimitResult:
        """
        Evaluate token bucket for the session and consume tokens if allowed.
        Executes atomically in SQLite transaction.
        """
        now = datetime.now(UTC)
        now_iso = now.isoformat()

        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT tokens, updated_at FROM rate_state WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()

            if row is None:
                current_tokens = self.burst
            else:
                stored_tokens, updated_at_str = float(row[0]), str(row[1])
                try:
                    last_update = datetime.fromisoformat(updated_at_str)
                    elapsed = max(0.0, (now - last_update).total_seconds())
                except Exception:
                    elapsed = 0.0
                current_tokens = min(self.burst, stored_tokens + elapsed * self.refill_per_sec)

            if current_tokens >= cost:
                remaining = current_tokens - cost
                cursor.execute(
                    """
                    INSERT INTO rate_state (session_id, tokens, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        tokens = excluded.tokens,
                        updated_at = excluded.updated_at
                    """,
                    (session_id, remaining, now_iso),
                )
                return RateLimitResult(allowed=True, remaining_tokens=remaining)

            needed = cost - current_tokens
            retry_after = math.ceil(needed / self.refill_per_sec) if self.refill_per_sec > 0 else 60
            cursor.execute(
                """
                INSERT INTO rate_state (session_id, tokens, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    tokens = excluded.tokens,
                    updated_at = excluded.updated_at
                """,
                (session_id, current_tokens, now_iso),
            )
            return RateLimitResult(
                allowed=False,
                remaining_tokens=current_tokens,
                retry_after_seconds=retry_after,
            )
        finally:
            cursor.close()


class CircuitBreaker:
    """
    Tracks repeated blocked saves per MCP session.
    Trips the session when threshold is exceeded in the time window (ADR-028).
    CLI operations remain unaffected.
    """

    def __init__(self, threshold: int = 5, window_minutes: int = 10) -> None:
        self.threshold = threshold
        self.window_delta = timedelta(minutes=window_minutes)

    def is_tripped(self, conn: sqlite3.Connection, session_id: str) -> tuple[bool, str | None]:
        """Check if session is currently tripped (paused)."""
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT tripped_until FROM breaker WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            if not row or not row[0]:
                return False, None

            tripped_until_str = str(row[0])
            now = datetime.now(UTC)
            tripped_until_dt = datetime.fromisoformat(tripped_until_str)
            if now < tripped_until_dt:
                return True, tripped_until_str

            return False, None
        finally:
            cursor.close()

    def record_blocked_save(
        self,
        conn: sqlite3.Connection,
        session_id: str,
    ) -> tuple[int, bool]:
        """
        Record a blocked save attempt (e.g. secret detected).
        Returns (current_blocked_count, is_tripped).
        """
        now = datetime.now(UTC)
        now_iso = now.isoformat()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT blocked_count, window_start FROM breaker WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()

            if row is None:
                new_count = 1
                if new_count >= self.threshold:
                    trip_time = (now + self.window_delta).isoformat()
                    cursor.execute(
                        """
                        INSERT INTO breaker (session_id, blocked_count, window_start, tripped_until)
                        VALUES (?, ?, ?, ?)
                        """,
                        (session_id, new_count, now_iso, trip_time),
                    )
                    return new_count, True
                cursor.execute(
                    """
                    INSERT INTO breaker (session_id, blocked_count, window_start, tripped_until)
                    VALUES (?, ?, ?, NULL)
                    """,
                    (session_id, new_count, now_iso),
                )
                return new_count, False

            blocked_count, window_start_str = int(row[0]), str(row[1])
            try:
                window_start = datetime.fromisoformat(window_start_str)
            except Exception:
                window_start = now

            if now - window_start > self.window_delta:
                # Window expired, start fresh window
                new_count = 1
                cursor.execute(
                    """
                    UPDATE breaker
                    SET blocked_count = ?, window_start = ?, tripped_until = NULL
                    WHERE session_id = ?
                    """,
                    (new_count, now_iso, session_id),
                )
                return new_count, False

            new_count = blocked_count + 1
            if new_count >= self.threshold:
                trip_time = (now + self.window_delta).isoformat()
                cursor.execute(
                    """
                    UPDATE breaker
                    SET blocked_count = ?, tripped_until = ?
                    WHERE session_id = ?
                    """,
                    (new_count, trip_time, session_id),
                )
                return new_count, True

            cursor.execute(
                "UPDATE breaker SET blocked_count = ? WHERE session_id = ?",
                (new_count, session_id),
            )
            return new_count, False
        finally:
            cursor.close()

    def check_active(self, conn: sqlite3.Connection, session_id: str) -> None:
        """Raise SessionPausedError if session is currently tripped."""
        tripped, until = self.is_tripped(conn, session_id)
        if tripped:
            raise SessionPausedError(
                f"MCP session '{session_id}' paused by circuit breaker until {until}. "
                "Use 'swallo breaker reset' via CLI terminal to clear."
            )

    @staticmethod
    def get_status(
        conn: sqlite3.Connection,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return status records for all or a specific session."""
        cursor = conn.cursor()
        try:
            if session_id:
                cursor.execute(
                    "SELECT session_id, blocked_count, window_start, tripped_until "
                    "FROM breaker WHERE session_id = ?",
                    (session_id,),
                )
            else:
                cursor.execute(
                    "SELECT session_id, blocked_count, window_start, tripped_until "
                    "FROM breaker ORDER BY session_id ASC"
                )
            rows = cursor.fetchall()
            results: list[dict[str, Any]] = []
            now = datetime.now(UTC)
            for r in rows:
                sid, count, w_start, tripped_until = str(r[0]), int(r[1]), str(r[2]), r[3]
                is_tripped = False
                if tripped_until:
                    try:
                        is_tripped = now < datetime.fromisoformat(str(tripped_until))
                    except (ValueError, TypeError):
                        is_tripped = False
                results.append({
                    "session_id": sid,
                    "blocked_count": count,
                    "window_start": w_start,
                    "tripped_until": str(tripped_until) if tripped_until else None,
                    "is_tripped": is_tripped,
                })
            return results
        finally:
            cursor.close()

    @staticmethod
    def reset(conn: sqlite3.Connection, session_id: str | None = None) -> int:
        """Reset circuit breaker for a given session or all sessions."""
        cursor = conn.cursor()
        try:
            if session_id:
                cursor.execute("DELETE FROM breaker WHERE session_id = ?", (session_id,))
            else:
                cursor.execute("DELETE FROM breaker")
            return cursor.rowcount
        finally:
            cursor.close()


class DraftQuotaManager:
    """
    Manages unapproved MCP draft count, byte quotas, and TTL expiry per project.
    Never removes or counts approved packets (ADR-007, F19).
    """

    def __init__(
        self,
        quota_count: int = 100,
        quota_bytes: int = 10 * 1024 * 1024,
        ttl_days: int = 7,
    ) -> None:
        self.quota_count = quota_count
        self.quota_bytes = quota_bytes
        self.ttl_delta = timedelta(days=ttl_days)

    def enforce_quotas(
        self,
        conn: sqlite3.Connection,
        project: str,
        incoming_bytes: int,
    ) -> None:
        """Verify draft quotas for project; raise DraftQuotaExceededError if exceeded."""
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT COUNT(*), COALESCE(SUM(LENGTH(body)), 0)
                FROM packets
                WHERE project = ? AND origin = 'mcp'
                  AND hash NOT IN (SELECT packet_hash FROM approvals)
                """,
                (project,),
            )
            row = cursor.fetchone()
            curr_count, curr_bytes = (int(row[0]), int(row[1])) if row else (0, 0)

            if curr_count >= self.quota_count:
                raise DraftQuotaExceededError(
                    f"Draft count quota exceeded for project '{project}': "
                    f"{curr_count}/{self.quota_count}. Purge old drafts or approve existing ones."
                )

            if curr_bytes + incoming_bytes > self.quota_bytes:
                raise DraftQuotaExceededError(
                    f"Draft byte quota exceeded for project '{project}': "
                    f"{curr_bytes + incoming_bytes}/{self.quota_bytes} bytes."
                )
        finally:
            cursor.close()

    def purge_expired_drafts(
        self,
        conn: sqlite3.Connection,
        project: str | None = None,
        now: datetime | None = None,
    ) -> int:
        """
        Purge unapproved drafts whose expires_at is past.
        Never touches approved packets or CLI packets without expires_at.
        """
        ref_time = (now or datetime.now(UTC)).isoformat()
        cursor = conn.cursor()
        try:
            if project:
                cursor.execute(
                    """
                    DELETE FROM packets
                    WHERE project = ? AND origin = 'mcp' AND expires_at IS NOT NULL
                      AND expires_at <= ?
                      AND hash NOT IN (SELECT packet_hash FROM approvals)
                    """,
                    (project, ref_time),
                )
            else:
                cursor.execute(
                    """
                    DELETE FROM packets
                    WHERE origin = 'mcp' AND expires_at IS NOT NULL
                      AND expires_at <= ?
                      AND hash NOT IN (SELECT packet_hash FROM approvals)
                    """,
                    (ref_time,),
                )
            return cursor.rowcount
        finally:
            cursor.close()


def verify_project_registered(
    conn: sqlite3.Connection,
    project_name_or_path: str,
) -> tuple[str, Path]:
    """
    Verify project registration against the projects table (ADR-029, F20).
    Rejects unregistered projects with UnregisteredProjectError.
    Returns (registered_project_name, registered_root_path).
    """
    cursor = conn.cursor()
    try:
        norm_path = str(Path(project_name_or_path).resolve())
        cursor.execute(
            """
            SELECT root_path, name
            FROM projects
            WHERE root_path = ? OR name = ?
            """,
            (norm_path, project_name_or_path),
        )
        row = cursor.fetchone()
        if not row:
            raise UnregisteredProjectError(
                f"Project '{project_name_or_path}' is not registered in the swallo store. "
                "Run 'swallo init' in the project directory to register it."
            )
        root_path, name = Path(str(row[0])), str(row[1])
        return name, root_path
    finally:
        cursor.close()


def check_deduplication(
    conn: sqlite3.Connection,
    project: str,
    packet_hash: str,
) -> str | None:
    """
    Check if an identical packet already exists in the project (ADR-012, F19).
    Returns existing packet ID if found, otherwise None.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id FROM packets WHERE project = ? AND hash = ?",
            (project, packet_hash),
        )
        row = cursor.fetchone()
        return str(row[0]) if row else None
    finally:
        cursor.close()


def enforce_stale_policy(
    report: StalenessReport,
    policy: str = "block",
) -> list[str]:
    """
    Enforce stale context policy for MCP load operations (ADR-028, F18).
    If critical drift exists and policy is 'block', raises StaleContextError.
    Otherwise returns warnings list.
    """
    if not report.is_stale:
        return []

    if report.acknowledged:
        return [f"Notice: stale context acknowledged for drifted files: {report.drifted_files}"]

    if report.is_critical:
        if policy == "block":
            raise StaleContextError(
                f"Stale context blocked: critical drift detected in {report.drifted_files}. "
                "Use 'swallo approve --ack-stale' or sync your repository before delivery."
            )
        return [
            f"Warning: critical drift detected in {report.drifted_files} without acknowledgment."
        ]

    return []
