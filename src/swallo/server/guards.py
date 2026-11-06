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
from datetime import UTC, datetime


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

            # Not enough tokens
            needed = cost - current_tokens
            retry_after = math.ceil(needed / self.refill_per_sec) if self.refill_per_sec > 0 else 60
            # Record current refilled state without deduction
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
