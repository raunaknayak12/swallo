"""
Unit and integration tests for Phase 2 Deterministic Correctness Benchmarks.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from benchmarks.deterministic.corpus import evaluate_corpus_redaction
from benchmarks.deterministic.defense_matrix import evaluate_defense_matrix
from benchmarks.deterministic.hash_stability import evaluate_hash_stability
from benchmarks.deterministic.invariants import evaluate_security_invariants
from benchmarks.deterministic.runner import run_deterministic_suite
from benchmarks.deterministic.sanitizer import evaluate_sanitizer
from benchmarks.deterministic.tamper_detection import evaluate_tamper_detection
from benchmarks.deterministic.variants import evaluate_decoded_variants
from swallo.bench.verify import verify_bench_results
from swallo.store import db, ledger


def test_corpus_redaction_evaluation() -> None:
    res = evaluate_corpus_redaction()
    assert res["pattern_precision"] == 1.0
    assert res["pattern_recall"] >= 0.8
    assert res["pattern_false_positive_rate"] == 0.0
    assert res["entropy_detector_false_positive_rate"] == 0.0
    assert res["corpus_total_samples"] >= 100
    assert res["total_positive_samples"] >= 80
    assert res["total_negative_samples"] >= 50


def test_decoded_variants_evaluation() -> None:
    res = evaluate_decoded_variants()
    assert res["base64_recall"] == 1.0
    assert res["hex_recall"] == 1.0
    assert res["url_recall"] == 1.0
    assert res["rot13_recall"] == 1.0
    assert res["reversal_recall"] == 1.0
    assert res["zero_width_recall"] == 1.0
    assert res["nested_depth_2_recall"] == 1.0
    assert res["nested_depth_3_recall"] == 1.0
    assert res["size_cap_exceeded_handled"] is True
    assert res["depth_cap_exceeded_handled"] is True


def test_canonical_hash_stability_evaluation() -> None:
    res = evaluate_hash_stability()
    assert res["key_order_invariance"] is True
    assert res["unicode_nfc_normalization"] is True
    assert res["volatile_fields_excluded"] is True
    assert res["float_rejected"] is True
    assert res["nan_rejected"] is True
    assert res["inf_rejected"] is True
    assert res["safe_int_boundary_accepted"] is True
    assert res["exceeded_int_boundary_rejected"] is True


def test_defense_matrix_evaluation() -> None:
    res = evaluate_defense_matrix()
    assert res["defense_matrix_pass_rate"] == 1.0
    assert res["zip_slip_relative_blocked"] is True
    assert res["zip_slip_absolute_blocked"] is True
    assert res["zip_slip_backslash_blocked"] is True
    assert res["member_count_limit_blocked"] is True
    assert res["uncompressed_size_limit_blocked"] is True
    assert res["compression_ratio_bomb_blocked"] is True
    assert res["json_max_depth_blocked"] is True


def test_sanitizer_evaluation() -> None:
    res = evaluate_sanitizer()
    assert res["sanitizer_overall_pass_rate"] == 1.0
    assert res["trojan_source_bidi_neutralized"] is True
    assert res["unicode_tag_chars_neutralized"] is True
    assert res["ansi_escapes_neutralized"] is True
    assert res["invisible_detection_recall"] == 1.0


def test_tamper_detection_evaluation() -> None:
    res = evaluate_tamper_detection()
    assert res["overall_tamper_detection_rate"] == 1.0
    assert res["event_log_tamper_detection_rate"] == 1.0
    assert res["ledger_tamper_detection_rate"] == 1.0


def test_tamper_detection_mac_starting_with_00() -> None:
    """
    Regression test for flaky tamper detection bug.

    When HMAC starts with '00', a naive mutation like `mac = '00' || substr(mac, 3)`
    is a silent no-op. The deterministic bit-flip ensures the row is altered,
    asserts before/after row change, and verifies ledger detects the tamper.
    """
    conn = sqlite3.connect(":memory:")
    db.apply_migrations(conn)

    # Key index 209 produces HMAC-SHA256 starting with '00' for this payload
    key = (209).to_bytes(32, "big")
    pkt_hash = "a" * 64
    target = "antigravity"
    ts = "2026-11-15T00:00:00Z"

    ledger.approve(conn, key, pkt_hash, target, ts=ts)
    row = conn.execute(
        "SELECT mac FROM approvals WHERE packet_hash = ?", (pkt_hash,)
    ).fetchone()
    assert row is not None
    original_mac = row[0]
    assert original_mac.startswith("00"), f"Expected MAC starting with '00', got {original_mac}"
    assert ledger.is_approved(conn, key, pkt_hash, target) is True

    # Check that the old buggy SQL would have been a silent no-op
    buggy_mutated_mac = "00" + original_mac[2:]
    assert (
        buggy_mutated_mac == original_mac
    ), "Expected buggy SQL to be a silent no-op on '00' prefix"

    # Now apply the robust bit-flip mutation
    mutation_sql = (
        "UPDATE approvals SET mac = "
        "CASE WHEN substr(mac, 1, 1) = '0' THEN '1' || substr(mac, 2) "
        "ELSE '0' || substr(mac, 2) END"
    )
    rows_before = conn.execute(
        "SELECT packet_hash, target, approved_at, mac FROM approvals"
    ).fetchall()
    conn.execute(mutation_sql)
    conn.commit()
    rows_after = conn.execute(
        "SELECT packet_hash, target, approved_at, mac FROM approvals"
    ).fetchall()

    # Precondition assertion: the row MUST have changed
    assert rows_before != rows_after, "Mutation was an undetected no-op"

    # Ledger MUST detect tampering
    assert ledger.is_approved(conn, key, pkt_hash, target) is False


def test_security_invariants_evaluation() -> None:
    res = evaluate_security_invariants()
    assert res["all_invariants_hold"] is True
    assert res["mcp_tool_list_has_no_approve"] is True
    assert res["circuit_breaker_trips_at_5"] is True
    assert res["circuit_breaker_persists_across_restart"] is True
    assert res["token_bucket_burst_enforced"] is True
    assert res["draft_quota_enforced"] is True
    assert res["stale_packet_blocked_by_default"] is True


def test_deterministic_runner_and_verify(tmp_path: Path) -> None:
    out_file = tmp_path / "deterministic.json"
    data = run_deterministic_suite(out_path=out_file)
    assert data["schema_version"] == "0.1"
    assert data["deterministic_summary"]["all_defenses_passed"] is True

    valid, logs = verify_bench_results(out_file)
    assert valid is True
    assert any("All invariants hold" in line for line in logs)
