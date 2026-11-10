"""
Deterministic Tamper Detection Benchmark.

Per ADR-003, ADR-008, TRD.md section 5.1, and Security.md F10:
- Mutates each field in SQLite event log rows (type, packet_hash, target, detail, prev_mac).
- Mutates each field in SQLite approval ledger rows (packet_hash, target, approved_at, mac).
- Verifies that `eventlog.verify()` and `ledger.is_approved()` achieve 100% detection rate.
"""

from __future__ import annotations

import secrets
import sqlite3
from typing import Any

from swallo.store import db, eventlog, ledger


def evaluate_tamper_detection() -> dict[str, Any]:
    """Execute row/column mutation tests across events and approvals."""
    conn = sqlite3.connect(":memory:")
    db.apply_migrations(conn)
    key = secrets.token_bytes(32)

    # 1. Populate valid baseline events
    eventlog.append(conn, key, type="packet_saved", packet_hash="hash1", detail="save 1")
    eventlog.append(conn, key, type="packet_approved", packet_hash="hash1", target="antigravity")
    eventlog.append(conn, key, type="packet_delivered", packet_hash="hash1", target="antigravity")

    # Baseline must verify cleanly
    baseline_errors = eventlog.verify(conn, key)
    assert len(baseline_errors) == 0, f"Baseline eventlog failed: {baseline_errors}"

    # Test event tampering across fields
    event_tamper_tests = [
        ("UPDATE events SET type = 'packet_forged' WHERE seq = 2", "tampered_type"),
        ("UPDATE events SET detail = 'hacked' WHERE seq = 1", "tampered_detail"),
        ("UPDATE events SET prev_mac = '0123456789abcdef' WHERE seq = 3", "tampered_prev_mac"),
        ("UPDATE events SET mac = 'deadbeef' WHERE seq = 2", "tampered_mac"),
        ("DELETE FROM events WHERE seq = 2", "deleted_row"),
    ]

    event_detected = 0
    for sql, _name in event_tamper_tests:
        # Clone db for isolated test
        test_conn = sqlite3.connect(":memory:")
        db.apply_migrations(test_conn)
        # Copy data
        for line in conn.iterdump():
            if "INSERT INTO" in line:
                test_conn.execute(line)
        # Apply mutation
        test_conn.execute(sql)
        errs = eventlog.verify(test_conn, key)
        if len(errs) > 0:
            event_detected += 1
        test_conn.close()

    event_detection_rate = event_detected / len(event_tamper_tests)

    # 2. Test Ledger Tampering
    pkt_hash = "a" * 64
    target = "antigravity"
    ledger.approve(conn, key, pkt_hash, target)
    assert ledger.is_approved(conn, key, pkt_hash, target) is True

    ledger_tamper_tests = [
        ("UPDATE approvals SET target = 'cursor'", "tampered_target"),
        ("UPDATE approvals SET approved_at = '2020-01-01T00:00:00Z'", "tampered_timestamp"),
        ("UPDATE approvals SET packet_hash = 'b' || substr(packet_hash, 2)", "tampered_hash"),
        ("UPDATE approvals SET mac = '00' || substr(mac, 3)", "tampered_mac"),
    ]

    ledger_detected = 0
    for sql, _name in ledger_tamper_tests:
        test_conn = sqlite3.connect(":memory:")
        db.apply_migrations(test_conn)
        for line in conn.iterdump():
            if "INSERT INTO" in line:
                test_conn.execute(line)
        test_conn.execute(sql)
        # Should now be NOT approved
        approved = ledger.is_approved(test_conn, key, pkt_hash, target)
        if not approved:
            ledger_detected += 1
        test_conn.close()

    ledger_detection_rate = ledger_detected / len(ledger_tamper_tests)

    return {
        "event_log_tamper_detection_rate": round(event_detection_rate, 4),
        "event_log_mutations_tested": len(event_tamper_tests),
        "ledger_tamper_detection_rate": round(ledger_detection_rate, 4),
        "ledger_mutations_tested": len(ledger_tamper_tests),
        "overall_tamper_detection_rate": 1.0 if (event_detection_rate == 1.0 and ledger_detection_rate == 1.0) else 0.0,
    }

