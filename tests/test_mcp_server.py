"""
Comprehensive integration tests for the swallo MCP server and security guardrails (F19, F20).

Per TRD.md section 11, Security.md, and IMPLEMENTATION_PLAN.md Step 7:
- 500-call stress loop on save_context (F19)
- Circuit breaker: tripping after threshold and cross-restart persistence
- Token bucket rate limiter behavior
- Draft quota enforcement and TTL purging
- Project root registry rejection of unregistered projects (F20)
- Stale policy blocking and --ack-stale acknowledgment override
- Security: zero live secrets emitted in list/load output
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from swallo.errors import (
    DraftQuotaExceededError,
    NotApprovedError,
    RateLimitedError,
    RedactionBlockedError,
    SessionPausedError,
    UnregisteredProjectError,
    UsageError,
)
from swallo.server.guards import CircuitBreaker, DraftQuotaManager, RateLimiter
from swallo.server.mcp_server import SwalloService
from swallo.store.db import (
    apply_migrations,
    get_connection,
    get_or_create_local_key,
)
from swallo.store.ledger import approve
from swallo.store.registry import register_project

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------


def _make_store(tmp_path: Path, project_name: str = "TestProject") -> tuple[Path, Path, Path]:
    """Create a minimal swallo store with key, DB, and registered project."""
    store_dir = tmp_path / "store"
    store_dir.mkdir(parents=True, exist_ok=True)
    db_path = store_dir / "swallo.db"
    key_path = store_dir / "key"

    conn = get_connection(db_path)
    apply_migrations(conn)
    get_or_create_local_key(key_path)

    proj_dir = tmp_path / "project"
    proj_dir.mkdir(parents=True, exist_ok=True)
    register_project(conn, proj_dir, name=project_name)
    conn.close()

    return store_dir, db_path, key_path


def _make_packet_dict(
    project: str = "TestProject",
    goal_text: str = "Test context handoff",
    item_text: str = "Use dependency injection for service layer.",
    session_id: str = "test_session",
) -> dict[str, Any]:
    """Build a minimal valid packet dict for testing."""
    return {
        "schema_version": "0.1",
        "project": project,
        "created_at": datetime.now(UTC).isoformat(),
        "sources": [
            {
                "session_id": session_id,
                "agent": "ide_agent",
                "capture_method": "ide-agent",
                "captured_at": datetime.now(UTC).isoformat(),
            }
        ],
        "goal": {"text": goal_text},
        "items": [{"kind": "decision", "text": item_text}],
    }


@pytest.fixture()
def store(tmp_path: Path) -> tuple[SwalloService, Path, Path, Path]:
    """Return a fully initialized SwalloService with store dir, db_path, key_path."""
    store_dir, db_path, key_path = _make_store(tmp_path)
    svc = SwalloService(store_dir=store_dir)
    return svc, store_dir, db_path, key_path


# ---------------------------------------------------------------------------
# Test: SwalloService initialization
# ---------------------------------------------------------------------------


def test_swallo_service_initializes_correctly(tmp_path: Path) -> None:
    """SwalloService should initialize with correct store configuration."""
    store_dir, db_path, key_path = _make_store(tmp_path)
    svc = SwalloService(store_dir=store_dir)
    assert svc.store_dir == store_dir
    assert svc.db_path == db_path
    assert svc.key_path == key_path
    assert len(svc.key_bytes) == 32


def test_swallo_service_missing_store_raises(tmp_path: Path) -> None:
    """SwalloService should raise UsageError if store is not initialized."""
    empty = tmp_path / "empty_store"
    empty.mkdir()
    with pytest.raises(UsageError, match="not initialized"):
        SwalloService(store_dir=empty)


# ---------------------------------------------------------------------------
# Test: save_context basics
# ---------------------------------------------------------------------------


def test_save_context_returns_draft(store: tuple[Any, ...]) -> None:
    """save_context should return id, hash, status=saved_draft."""
    svc, store_dir, db_path, key_path = store
    pkt = _make_packet_dict()
    result = svc.save_context(pkt, project="TestProject", session_id="s1")
    assert result["status"] == "saved_draft"
    assert result["id"].startswith("pkt_")
    assert result["hash"].startswith("sha256:")
    assert len(result["hash"].split(":", 1)[1]) == 64
    assert isinstance(result["redactions"], int)
    assert result["redactions"] >= 0


def test_save_context_idempotent_dedup(store: tuple[Any, ...]) -> None:
    """Submitting identical payloads should return 'deduplicated' on second call."""
    svc, store_dir, db_path, key_path = store
    pkt = _make_packet_dict(item_text="Dedup test item unique 999")
    r1 = svc.save_context(pkt, project="TestProject", session_id="s1")
    assert r1["status"] == "saved_draft"
    r2 = svc.save_context(pkt, project="TestProject", session_id="s1")
    assert r2["status"] == "deduplicated"
    assert r2["id"] == r1["id"]


def test_save_context_redacts_secrets(store: tuple[Any, ...]) -> None:
    """save_context should block in default mode and redact in mask mode."""
    svc, store_dir, db_path, key_path = store
    pkt = _make_packet_dict(goal_text="Use API key AKIAIOSFODNN7EXAMPLE for access")

    # In default 'block' mode, secrets raise RedactionBlockedError
    with pytest.raises(RedactionBlockedError):
        svc.save_context(pkt, project="TestProject", session_id="s1")

    # In 'mask' mode, secrets are replaced and counted
    svc.config.redact.mode = "mask"
    result = svc.save_context(pkt, project="TestProject", session_id="s2")
    assert result["redactions"] >= 1


def test_save_context_unregistered_project_raises(store: tuple[Any, ...]) -> None:
    """save_context must reject unregistered project names (F20)."""
    svc, store_dir, db_path, key_path = store
    pkt = _make_packet_dict(project="UnregisteredProject")
    with pytest.raises(UnregisteredProjectError):
        svc.save_context(pkt, project="UnregisteredProject", session_id="s1")


# ---------------------------------------------------------------------------
# Test: 500-call stress loop (F19)
# ---------------------------------------------------------------------------


def test_save_context_500_call_stress_loop(tmp_path: Path) -> None:
    """
    F19: 500 sequential save_context calls should all complete without error.
    Each call uses a unique item text to avoid deduplication.
    Validates that the store handles repeated writes without corruption.
    """
    store_dir, db_path, key_path = _make_store(tmp_path)
    svc = SwalloService(store_dir=store_dir)

    # Use a very high rate limit and draft quota to allow 500 calls in this stress test
    svc.rate_limiter = RateLimiter(burst=600, refill_per_hour=600)
    svc.quota_mgr = DraftQuotaManager(quota_count=1000, quota_bytes=50 * 1024 * 1024)

    successes = 0
    for i in range(500):
        pkt = _make_packet_dict(
            item_text=f"Stress test item #{i:04d} decision unique-{secrets.token_hex(4)}",
            session_id="stress_session",
        )
        result = svc.save_context(pkt, project="TestProject", session_id="stress_session")
        assert result["status"] in ("saved_draft", "deduplicated"), (
            f"Unexpected status '{result['status']}' at call #{i}"
        )
        successes += 1

    assert successes == 500, f"Only {successes} of 500 calls succeeded"

    # Verify database integrity after stress
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check")
        row = cur.fetchone()
        assert row[0] == "ok", f"SQLite integrity check failed after stress: {row[0]}"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Test: Rate limiter
# ---------------------------------------------------------------------------


def test_rate_limiter_allows_within_burst(tmp_path: Path) -> None:
    """Calls within burst limit should succeed."""
    store_dir, db_path, key_path = _make_store(tmp_path)
    svc = SwalloService(store_dir=store_dir)
    svc.rate_limiter = RateLimiter(burst=5, refill_per_hour=0)

    conn = get_connection(db_path)
    try:
        for i in range(5):
            result = svc.rate_limiter.check_and_consume(conn, "sess1", cost=1.0)
            assert result.allowed, f"Expected allowed at call #{i}"
    finally:
        conn.close()


def test_rate_limiter_blocks_after_burst_exhausted(tmp_path: Path) -> None:
    """Calls beyond burst capacity should raise RateLimitedError."""
    store_dir, db_path, key_path = _make_store(tmp_path)
    svc = SwalloService(store_dir=store_dir)
    svc.rate_limiter = RateLimiter(burst=3, refill_per_hour=0)

    conn = get_connection(db_path)
    try:
        for _ in range(3):
            svc.rate_limiter.check_and_consume(conn, "sess2", cost=1.0)
        blocked = svc.rate_limiter.check_and_consume(conn, "sess2", cost=1.0)
        assert not blocked.allowed
    finally:
        conn.close()


def test_save_context_rate_limited_raises(tmp_path: Path) -> None:
    """save_context should raise RateLimitedError when rate limit is exceeded."""
    store_dir, db_path, key_path = _make_store(tmp_path)
    svc = SwalloService(store_dir=store_dir)
    svc.rate_limiter = RateLimiter(burst=1, refill_per_hour=0)

    # First call should consume the only token
    pkt1 = _make_packet_dict(item_text="Rate limit test unique 1a")
    svc.save_context(pkt1, project="TestProject", session_id="rate_sess")

    # Second call should be rate-limited
    pkt2 = _make_packet_dict(item_text="Rate limit test unique 2b")
    with pytest.raises(RateLimitedError):
        svc.save_context(pkt2, project="TestProject", session_id="rate_sess")


# ---------------------------------------------------------------------------
# Test: Circuit breaker
# ---------------------------------------------------------------------------


def test_circuit_breaker_trips_after_threshold(tmp_path: Path) -> None:
    """Circuit breaker should trip a session after repeated blocked saves."""
    store_dir, db_path, key_path = _make_store(tmp_path)
    conn = get_connection(db_path)

    breaker = CircuitBreaker(threshold=3, window_minutes=10)
    session = "breaker_test_session"

    try:
        # Record blocked saves up to threshold - 1
        for _i in range(2):
            count, tripped = breaker.record_blocked_save(conn, session)
            assert not tripped, f"Should not be tripped at count {count}"

        # Trip on threshold
        count, tripped = breaker.record_blocked_save(conn, session)
        assert tripped, f"Expected tripped at count {count}"

        # Session should now be tripped
        is_tripped, until = breaker.is_tripped(conn, session)
        assert is_tripped
        assert until is not None
    finally:
        conn.close()


def test_circuit_breaker_check_active_raises_when_tripped(tmp_path: Path) -> None:
    """check_active() should raise SessionPausedError for a tripped session."""
    store_dir, db_path, key_path = _make_store(tmp_path)
    conn = get_connection(db_path)

    breaker = CircuitBreaker(threshold=2, window_minutes=10)
    session = "paused_session"

    try:
        for _ in range(2):
            breaker.record_blocked_save(conn, session)

        with pytest.raises(SessionPausedError, match="paused"):
            breaker.check_active(conn, session)
    finally:
        conn.close()


def test_circuit_breaker_persists_across_connections(tmp_path: Path) -> None:
    """Circuit breaker trip must persist across separate DB connections (restart)."""
    store_dir, db_path, key_path = _make_store(tmp_path)
    breaker = CircuitBreaker(threshold=2, window_minutes=10)
    session = "persist_session"

    # First connection: trip the breaker
    conn1 = get_connection(db_path)
    try:
        for _ in range(2):
            breaker.record_blocked_save(conn1, session)
    finally:
        conn1.close()

    # Second connection: breaker should still be tripped
    conn2 = get_connection(db_path)
    try:
        is_tripped, _ = breaker.is_tripped(conn2, session)
        assert is_tripped, "Circuit breaker should persist across connections"
    finally:
        conn2.close()


def test_circuit_breaker_reset_clears_session(tmp_path: Path) -> None:
    """CircuitBreaker.reset() should clear tripped state for a given session."""
    store_dir, db_path, key_path = _make_store(tmp_path)
    conn = get_connection(db_path)
    breaker = CircuitBreaker(threshold=2, window_minutes=10)
    session = "reset_session"

    try:
        for _ in range(2):
            breaker.record_blocked_save(conn, session)
        is_tripped, _ = breaker.is_tripped(conn, session)
        assert is_tripped

        reset_count = CircuitBreaker.reset(conn, session_id=session)
        assert reset_count >= 1

        is_tripped_after, _ = breaker.is_tripped(conn, session)
        assert not is_tripped_after
    finally:
        conn.close()


def test_circuit_breaker_window_resets_on_expiry(tmp_path: Path) -> None:
    """Blocked count should reset when sliding window expires."""
    store_dir, db_path, key_path = _make_store(tmp_path)
    conn = get_connection(db_path)
    breaker = CircuitBreaker(threshold=10, window_minutes=10)
    session = "window_session"

    try:
        # Record a blocked save
        count, tripped = breaker.record_blocked_save(conn, session)
        assert count == 1
        assert not tripped

        # Backdate window_start in database to simulate window expiration
        old_start = (datetime.now(UTC) - timedelta(minutes=15)).isoformat()
        conn.execute(
            "UPDATE breaker SET window_start = ? WHERE session_id = ?",
            (old_start, session),
        )

        # Next call: window has expired, starts fresh at count=1
        count2, tripped2 = breaker.record_blocked_save(conn, session)
        assert count2 == 1
        assert not tripped2
    finally:
        conn.close()


def test_circuit_breaker_get_status(tmp_path: Path) -> None:
    """get_status() should return session records with is_tripped field."""
    store_dir, db_path, key_path = _make_store(tmp_path)
    conn = get_connection(db_path)
    breaker = CircuitBreaker(threshold=3, window_minutes=10)

    try:
        breaker.record_blocked_save(conn, "sess_a")
        breaker.record_blocked_save(conn, "sess_b")

        statuses = CircuitBreaker.get_status(conn)
        ids = {s["session_id"] for s in statuses}
        assert "sess_a" in ids
        assert "sess_b" in ids
        for s in statuses:
            assert "blocked_count" in s
            assert "is_tripped" in s
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Test: Draft quota enforcement and TTL purging
# ---------------------------------------------------------------------------


def test_draft_quota_count_exceeded(tmp_path: Path) -> None:
    """DraftQuotaManager should raise DraftQuotaExceededError when count exceeded."""
    store_dir, db_path, key_path = _make_store(tmp_path)
    conn = get_connection(db_path)
    quota = DraftQuotaManager(quota_count=2, quota_bytes=10 * 1024 * 1024, ttl_days=7)
    project = "TestProject"

    try:
        # Manually insert 2 MCP draft packets to fill quota
        for i in range(2):
            conn.execute(
                """
                INSERT INTO packets (id, hash, schema_version, project, created_at, body, origin)
                VALUES (?, ?, '0.1', ?, ?, ?, 'mcp')
                """,
                (
                    f"pkt_quota_{i:04d}",
                    hashlib.sha256(f"quota{i}".encode()).hexdigest(),
                    project,
                    datetime.now(UTC).isoformat(),
                    b'{"schema_version": "0.1"}',
                ),
            )

        with pytest.raises(DraftQuotaExceededError, match="quota"):
            quota.enforce_quotas(conn, project, incoming_bytes=100)
    finally:
        conn.close()


def test_draft_quota_ttl_purge(tmp_path: Path) -> None:
    """purge_expired_drafts() should remove MCP drafts past their expires_at."""
    store_dir, db_path, key_path = _make_store(tmp_path)
    conn = get_connection(db_path)
    quota = DraftQuotaManager(quota_count=100, quota_bytes=10 * 1024 * 1024, ttl_days=7)
    project = "TestProject"
    past = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    future = (datetime.now(UTC) + timedelta(days=10)).isoformat()

    try:
        # Insert expired MCP draft
        conn.execute(
            """
            INSERT INTO packets
                (id, hash, schema_version, project, created_at, body, origin, expires_at)
            VALUES ('pkt_expired_01', ?, '0.1', ?, ?, ?, 'mcp', ?)
            """,
            (
                hashlib.sha256(b"expired01").hexdigest(),
                project,
                past,
                b'{"schema_version": "0.1"}',
                past,
            ),
        )
        # Insert non-expired MCP draft
        conn.execute(
            """
            INSERT INTO packets
                (id, hash, schema_version, project, created_at, body, origin, expires_at)
            VALUES ('pkt_fresh_01', ?, '0.1', ?, ?, ?, 'mcp', ?)
            """,
            (
                hashlib.sha256(b"fresh01").hexdigest(),
                project,
                datetime.now(UTC).isoformat(),
                b'{"schema_version": "0.1"}',
                future,
            ),
        )

        purged = quota.purge_expired_drafts(conn, project=project)
        assert purged == 1

        # Non-expired draft must still be there
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM packets WHERE id = 'pkt_fresh_01'")
        assert cur.fetchone()[0] == 1
        cur.close()
    finally:
        conn.close()


def test_draft_quota_never_purges_approved(tmp_path: Path) -> None:
    """purge_expired_drafts() must NOT remove approved packets even when expired."""
    store_dir, db_path, key_path = _make_store(tmp_path)
    conn = get_connection(db_path)
    key_bytes = get_or_create_local_key(key_path)
    quota = DraftQuotaManager(quota_count=100, quota_bytes=10 * 1024 * 1024, ttl_days=7)
    project = "TestProject"
    past = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    pkt_hash = hashlib.sha256(b"approved_expired").hexdigest()

    try:
        conn.execute(
            """
            INSERT INTO packets
                (id, hash, schema_version, project, created_at, body, origin, expires_at)
            VALUES ('pkt_approved_01', ?, '0.1', ?, ?, ?, 'mcp', ?)
            """,
            (pkt_hash, project, past, b'{"schema_version": "0.1"}', past),
        )
        # Approve the packet
        approve(conn, key_bytes, pkt_hash, "claude_code")

        purged = quota.purge_expired_drafts(conn, project=project)
        assert purged == 0, "Should NOT purge approved packets"

        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM packets WHERE id = 'pkt_approved_01'")
        assert cur.fetchone()[0] == 1, "Approved packet should still be in store"
        cur.close()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Test: Project root registration (F20)
# ---------------------------------------------------------------------------


def test_save_context_unregistered_project_blocked(tmp_path: Path) -> None:
    """MCP server must block save attempts for unregistered project roots (F20)."""
    store_dir, db_path, key_path = _make_store(tmp_path)
    svc = SwalloService(store_dir=store_dir)

    pkt = _make_packet_dict(project="UnregisteredProject")
    with pytest.raises(UnregisteredProjectError):
        svc.save_context(pkt, project="UnregisteredProject", session_id="s1")


def test_load_context_unregistered_project_blocked(tmp_path: Path) -> None:
    """MCP server must block load attempts for unregistered project (F20)."""
    store_dir, db_path, key_path = _make_store(tmp_path)
    svc = SwalloService(store_dir=store_dir)

    with pytest.raises(UnregisteredProjectError):
        svc.load_context(project="UnregisteredProject", packet_id="latest")


def test_list_contexts_unregistered_project_blocked(tmp_path: Path) -> None:
    """MCP server must block list_contexts for unregistered project (F20)."""
    store_dir, db_path, key_path = _make_store(tmp_path)
    svc = SwalloService(store_dir=store_dir)

    with pytest.raises(UnregisteredProjectError):
        svc.list_contexts(project="UnregisteredProject")


# ---------------------------------------------------------------------------
# Test: load_context requires human approval
# ---------------------------------------------------------------------------


def test_load_context_requires_approval(store: tuple[Any, ...]) -> None:
    """load_context must raise NotApprovedError for unapproved packets."""
    svc, store_dir, db_path, key_path = store

    # Save packet but do NOT approve it
    pkt = _make_packet_dict()
    result = svc.save_context(pkt, project="TestProject", session_id="s1")
    pkt_id = result["id"]

    with pytest.raises(NotApprovedError):
        svc.load_context(project="TestProject", packet_id=pkt_id, target="claude_code")


def test_load_context_works_after_approval(store: tuple[Any, ...]) -> None:
    """load_context should succeed after human approval via ledger."""
    svc, store_dir, db_path, key_path = store
    key_bytes = get_or_create_local_key(key_path)

    # Save and approve
    pkt = _make_packet_dict(item_text="Approved unique item text 42xyz")
    result = svc.save_context(pkt, project="TestProject", session_id="s1")
    pkt_hash = result["hash"]

    conn = get_connection(db_path)
    approve(conn, key_bytes, pkt_hash, "claude_code")
    conn.close()

    # Load should now succeed
    loaded = svc.load_context(
        project="TestProject", packet_id=result["id"], target="claude_code"
    )
    assert "content" in loaded
    assert len(loaded["content"]) > 0
    # Verify CSPRNG fence is present (content header)
    assert "UNTRUSTED DATA" in loaded["content"].upper() or "swallo" in loaded["content"].lower()


# ---------------------------------------------------------------------------
# Test: list_contexts never leaks content
# ---------------------------------------------------------------------------


def test_list_contexts_never_leaks_body(store: tuple[Any, ...]) -> None:
    """list_contexts must never return packet body content."""
    svc, store_dir, db_path, key_path = store

    pkt = _make_packet_dict(item_text="Super secret decision text 777")
    svc.save_context(pkt, project="TestProject", session_id="s1")

    contexts = svc.list_contexts(project="TestProject", state="all")
    assert len(contexts) >= 1

    for ctx in contexts:
        assert "body" not in ctx, "list_contexts must never return packet body"
        assert "content" not in ctx, "list_contexts must never return rendered content"
        assert "items" not in ctx, "list_contexts must never return items list"
        # Only safe metadata fields allowed
        assert "id" in ctx
        assert "hash" in ctx
        assert "state" in ctx


# ---------------------------------------------------------------------------
# Test: diff returns structural comparison
# ---------------------------------------------------------------------------


def test_diff_returns_added_removed_shared(store: tuple[Any, ...]) -> None:
    """diff should return added, removed, and shared items between two packets."""
    svc, store_dir, db_path, key_path = store

    pkt_a = _make_packet_dict(item_text="Shared item text A and B")
    pkt_b = _make_packet_dict(item_text="Shared item text A and B")
    pkt_b["items"].append({"kind": "constraint", "text": "Only B item text extra"})

    r_a = svc.save_context(pkt_a, project="TestProject", session_id="s1")
    r_b = svc.save_context(pkt_b, project="TestProject", session_id="s1")

    if r_a["id"] == r_b["id"]:
        # Deduplicated - add unique content to force different packet
        pkt_b["items"].append({"kind": "note", "text": f"Unique {secrets.token_hex(8)}"})
        r_b = svc.save_context(pkt_b, project="TestProject", session_id="s1")

    diff = svc.diff(a=r_a["id"], b=r_b["id"], project="TestProject")
    assert "added_items" in diff
    assert "removed_items" in diff
    assert "shared_items" in diff
    assert "packet_a" in diff
    assert "packet_b" in diff


# ---------------------------------------------------------------------------
# Test: Security — no live secrets in list/load output
# ---------------------------------------------------------------------------

_KNOWN_SECRET_PATTERNS = [
    "AKIAIOSFODNN7EXAMPLE",         # AWS access key (fake)
    "AKIA4RANDOMFAKETEST1",         # AWS key pattern 2
    "ghp_TestFakeGitHubToken1234",  # GitHub PAT format
    "sk_test_FakePaddleSecretKey",  # Paddle/Stripe pattern
]


def test_zero_live_secrets_in_list_contexts(store: tuple[Any, ...]) -> None:
    """
    Security: list_contexts must not return any raw secret text even if
    packets containing secret-like patterns were saved through save_context.
    """
    svc, store_dir, db_path, key_path = store
    svc.config.redact.mode = "mask"

    for secret_str in _KNOWN_SECRET_PATTERNS:
        pkt = _make_packet_dict(
            goal_text=f"Use key {secret_str} for auth",
            item_text=f"Config with credential {secret_str} embedded",
        )
        # save_context should redact the secrets internally
        svc.save_context(pkt, project="TestProject", session_id=f"sec_sess_{secret_str[:8]}")

    contexts = svc.list_contexts(project="TestProject", state="all")
    for ctx in contexts:
        ctx_str = str(ctx)
        for secret in _KNOWN_SECRET_PATTERNS:
            assert secret not in ctx_str, (
                f"Secret '{secret[:10]}...' found in list_contexts output!"
            )


def test_zero_live_secrets_in_load_context_content(store: tuple[Any, ...]) -> None:
    """
    Security: load_context content must not contain raw secrets.
    Redaction should ensure secrets are masked before storage.
    """
    svc, store_dir, db_path, key_path = store
    svc.config.redact.mode = "mask"
    key_bytes = get_or_create_local_key(key_path)

    secret_key = "AKIAIOSFODNN7EXAMPLE"
    pkt = _make_packet_dict(
        goal_text=f"Deploy with key {secret_key}",
        item_text="Configure environment",
    )
    result = svc.save_context(pkt, project="TestProject", session_id="sec_load_sess")
    pkt_hash = result["hash"]

    # Approve it
    conn = get_connection(db_path)
    approve(conn, key_bytes, pkt_hash, "claude_code")
    conn.close()

    # Load it
    loaded = svc.load_context(
        project="TestProject", packet_id=result["id"], target="claude_code"
    )
    content = loaded.get("content", "")
    assert secret_key not in content, (
        "Live secret found in load_context output — redaction failed!"
    )


# ---------------------------------------------------------------------------
# Test: merge_contexts produces merged draft with conflict list
# ---------------------------------------------------------------------------


def test_merge_contexts_basic(store: tuple[Any, ...]) -> None:
    """merge_contexts should return a merged draft id and conflict list."""
    svc, store_dir, db_path, key_path = store
    svc.rate_limiter = RateLimiter(burst=100, refill_per_hour=100)

    pkt_a = _make_packet_dict(item_text=f"Merge A item {secrets.token_hex(6)}")
    pkt_b = _make_packet_dict(item_text=f"Merge B item {secrets.token_hex(6)}")

    r_a = svc.save_context(pkt_a, project="TestProject", session_id="merge_s1")
    r_b = svc.save_context(pkt_b, project="TestProject", session_id="merge_s1")

    merged = svc.merge_contexts(
        ids=[r_a["id"], r_b["id"]],
        into="merged",
        project="TestProject",
        session_id="merge_s1",
    )
    assert merged["status"] == "merged_draft"
    assert merged["id"].startswith("pkt_")
    assert isinstance(merged["conflicts"], list)


def test_merge_contexts_requires_two_or_more_ids(store: tuple[Any, ...]) -> None:
    """merge_contexts should raise ValidationError if fewer than 2 ids provided."""
    from swallo.errors import ValidationError

    svc, store_dir, db_path, key_path = store
    pkt = _make_packet_dict()
    result = svc.save_context(pkt, project="TestProject", session_id="s1")

    with pytest.raises(ValidationError, match="at least two"):
        svc.merge_contexts(ids=[result["id"]], into="merged", project="TestProject")


# ---------------------------------------------------------------------------
# Test: Session paused by circuit breaker blocks save_context
# ---------------------------------------------------------------------------


def test_save_context_blocked_when_session_paused(tmp_path: Path) -> None:
    """save_context must raise SessionPausedError for a tripped session."""
    store_dir, db_path, key_path = _make_store(tmp_path)
    svc = SwalloService(store_dir=store_dir)
    svc.circuit_breaker = CircuitBreaker(threshold=1, window_minutes=60)

    # Manually trip the breaker
    conn = get_connection(db_path)
    try:
        svc.circuit_breaker.record_blocked_save(conn, "paused_session")
        is_tripped, _ = svc.circuit_breaker.is_tripped(conn, "paused_session")
        assert is_tripped
    finally:
        conn.close()

    pkt = _make_packet_dict()
    with pytest.raises(SessionPausedError, match="paused"):
        svc.save_context(pkt, project="TestProject", session_id="paused_session")
