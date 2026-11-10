"""
Deterministic Security Invariants Benchmark.

Verifies fundamental architectural invariants:
1. MCP Tool List Invariant: Contains zero approve tools (ADR-007).
2. Circuit Breaker Persistence: Trips after 5 consecutive blocks; state persists in DB (ADR-028).
3. Token Bucket Invariant: Enforces configured burst (default burst=10).
4. Draft Quota Invariant: Raises DraftQuotaExceededError when count >= quota_count.
5. Staleness Drift Invariant: Stale+critical packets blocked on MCP load (policy='block').
"""

from __future__ import annotations

import sqlite3
from typing import Any

from swallo.errors import DraftQuotaExceededError, StaleContextError
from swallo.repo.staleness import StalenessReport
from swallo.server.guards import (
    CircuitBreaker,
    DraftQuotaManager,
    RateLimiter,
    enforce_stale_policy,
)
from swallo.server.mcp_server import SwalloService
from swallo.store import db


def evaluate_security_invariants() -> dict[str, Any]:
    """Test and verify all security invariants."""
    results: dict[str, Any] = {}

    # 1. Invariant: MCP Tool List Contains No Approve Tool
    # Public methods on SwalloService correspond to registered MCP tools.
    service_methods = [
        m for m in dir(SwalloService)
        if not m.startswith("_") and callable(getattr(SwalloService, m))
    ]
    has_approve_tool = any("approve" in m.lower() for m in service_methods)
    results["mcp_tool_list_has_no_approve"] = not has_approve_tool

    # 2. Invariant: Circuit Breaker Trips After 5 Blocks and Persists
    conn = sqlite3.connect(":memory:")
    db.apply_migrations(conn)
    breaker = CircuitBreaker(threshold=5, window_minutes=10)
    session_id = "sess_bench_test"

    # First 4 saves must NOT trip the breaker
    for _ in range(4):
        count, tripped = breaker.record_blocked_save(conn, session_id)
        assert tripped is False, f"Breaker should not trip before threshold; count={count}"

    # 5th block must trip the breaker
    count5, tripped5 = breaker.record_blocked_save(conn, session_id)
    results["circuit_breaker_trips_at_5"] = bool(count5 == 5 and tripped5 is True)

    # Persistence check: re-instantiate breaker on the same connection (simulating restart)
    breaker_restarted = CircuitBreaker(threshold=5, window_minutes=10)
    is_tripped, _ = breaker_restarted.is_tripped(conn, session_id)
    results["circuit_breaker_persists_across_restart"] = bool(is_tripped is True)

    # 3. Invariant: Token Bucket (Burst=10 by default)
    # refill_per_hour=0 ensures no refill occurs during the test
    limiter = RateLimiter(burst=10, refill_per_hour=0)
    rate_session = "sess_rate_test"

    # Consume all 10 tokens — all should be allowed
    all_passed = True
    for _ in range(10):
        res = limiter.check_and_consume(conn, rate_session, cost=1.0)
        if not res.allowed:
            all_passed = False

    # 11th request must be rejected (burst exhausted, no refill)
    res_11 = limiter.check_and_consume(conn, rate_session, cost=1.0)
    results["token_bucket_burst_enforced"] = bool(all_passed and not res_11.allowed)

    # 4. Invariant: Draft Quota (quota_count=5 for a quick test)
    # enforce_quotas raises DraftQuotaExceededError when count >= quota_count
    quota_mgr = DraftQuotaManager(quota_count=5, quota_bytes=10 * 1024 * 1024)
    cursor = conn.cursor()
    # Insert exactly 5 unapproved MCP drafts (origin='mcp', no matching approvals)
    for i in range(5):
        cursor.execute(
            """
            INSERT INTO packets (id, hash, schema_version, project, created_at, origin, body)
            VALUES (?, ?, '0.1', ?, '2026-01-01T00:00:00+00:00', 'mcp', ?)
            """,
            (f"pkt_draft_{i:04d}", f"hash_{i:04d}", "bench_proj", b"{}"),
        )
    conn.commit()

    # 5th draft brings us to quota; next incoming packet must be rejected
    quota_exceeded = False
    try:
        quota_mgr.enforce_quotas(conn, "bench_proj", incoming_bytes=100)
    except DraftQuotaExceededError:
        quota_exceeded = True
    results["draft_quota_enforced"] = quota_exceeded

    # 5. Invariant: Stale+Critical Packet Blocked Unless Acknowledged
    # enforce_stale_policy raises StaleContextError when is_stale=True, is_critical=True,
    # acknowledged=False, and policy='block' (the default).
    stale_report = StalenessReport(
        is_stale=True,
        is_critical=True,
        acknowledged=False,
        head_commit="head123",
        packet_commit="head000",
    )

    stale_blocked = False
    try:
        enforce_stale_policy(stale_report, policy="block")
    except StaleContextError:
        stale_blocked = True
    results["stale_packet_blocked_by_default"] = stale_blocked

    results["all_invariants_hold"] = bool(all(results.values()))
    conn.close()
    return results
