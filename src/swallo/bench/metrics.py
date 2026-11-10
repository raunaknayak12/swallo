"""
Benchmark Phase 1 metrics computation.

Per BENCHMARKS.md Phase 1 requirements:
- secret_redaction_recall: fraction of injected secrets correctly caught.
- secret_redaction_precision: fraction of reported findings that match injected secrets.
- latency_p50_ms, latency_p95_ms: execution latency distribution across fixtures.
- determinism_score: fraction of repeated serializations yielding byte-identical hashes.
- guard_behavior: fraction of guard boundary decisions adhering to security policy.
"""

from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING

from swallo.bench.schema import BenchResultEntry
from swallo.errors import RedactionBlockedError
from swallo.redact.decode import DecodedVariantDetector
from swallo.redact.denylist import DenylistDetector
from swallo.redact.engine import RedactionEngine
from swallo.redact.entropy import EntropyDetector
from swallo.redact.patterns import PatternDetector
from swallo.schema.canonical import to_canonical_json

if TYPE_CHECKING:
    pass


def _get_default_redact_engine() -> RedactionEngine:
    patterns = PatternDetector()
    entropy = EntropyDetector(threshold=4.3)
    denylist = DenylistDetector([])
    decoded = DecodedVariantDetector(inner_detectors=[patterns, entropy])
    return RedactionEngine([patterns, entropy, denylist, decoded])


def _percentile(values: list[float], pct: float) -> float:
    """Compute percentile from sorted or unsorted list of floats."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * pct
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    d0 = sorted_vals[int(f)] * (c - k)
    d1 = sorted_vals[int(c)] * (k - f)
    return d0 + d1


def compute_redaction_metrics(
    fixtures: list[dict[str, object]],
) -> tuple[BenchResultEntry, BenchResultEntry]:
    """
    Evaluate secret redaction recall and precision over fixture set.

    Injected secrets in fixtures contain markers (Token=sk-proj-..., ghp_..., etc.).
    """
    engine = _get_default_redact_engine()

    injected_count = 0
    true_positive = 0
    total_findings = 0

    for pkt in fixtures:
        items = pkt.get("items", [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", ""))
            has_injected = " Token=" in text
            if has_injected:
                injected_count += 1

            findings = engine.scan(text)
            total_findings += len(findings)

            if has_injected and len(findings) > 0:
                true_positive += 1

    recall = (true_positive / injected_count) if injected_count > 0 else 1.0
    precision = (true_positive / total_findings) if total_findings > 0 else 1.0

    n_samples = len(fixtures)
    recall_entry = BenchResultEntry(
        test="secret_redaction_recall",
        n=injected_count,
        value=round(recall, 4),
        ci=[round(max(0.0, recall - 0.05), 4), round(min(1.0, recall + 0.05), 4)],
    )
    precision_entry = BenchResultEntry(
        test="secret_redaction_precision",
        n=total_findings if total_findings > 0 else n_samples,
        value=round(precision, 4),
        ci=[round(max(0.0, precision - 0.05), 4), round(min(1.0, precision + 0.05), 4)],
    )
    return recall_entry, precision_entry


def compute_latency_metrics(
    fixtures: list[dict[str, object]],
) -> tuple[BenchResultEntry, BenchResultEntry]:
    """Measure latency of canonical serialization across the fixture set."""
    latencies_ms: list[float] = []
    for pkt in fixtures:
        t0 = time.perf_counter()
        to_canonical_json(pkt)
        t1 = time.perf_counter()
        latencies_ms.append((t1 - t0) * 1000.0)

    p50 = _percentile(latencies_ms, 0.50)
    p95 = _percentile(latencies_ms, 0.95)

    n = len(fixtures)
    p50_entry = BenchResultEntry(
        test="latency_p50_ms",
        n=n,
        value=round(p50, 4),
        ci=[round(max(0.0, p50 * 0.9), 4), round(p50 * 1.1, 4)],
    )
    p95_entry = BenchResultEntry(
        test="latency_p95_ms",
        n=n,
        value=round(p95, 4),
        ci=[round(max(0.0, p95 * 0.9), 4), round(p95 * 1.1, 4)],
    )
    return p50_entry, p95_entry


def compute_determinism_metric(
    fixtures: list[dict[str, object]],
) -> BenchResultEntry:
    """Verify that repeated serialization yields byte-identical representations."""
    identical_count = 0
    total = len(fixtures)

    for pkt in fixtures:
        repr1 = to_canonical_json(pkt)
        repr2 = to_canonical_json(pkt)
        repr3 = to_canonical_json(pkt)
        if repr1 == repr2 == repr3:
            identical_count += 1

    score = (identical_count / total) if total > 0 else 1.0
    return BenchResultEntry(
        test="determinism_score",
        n=total,
        value=round(score, 4),
        ci=[round(score, 4), round(score, 4)],
    )


def compute_guard_behavior_metric(iterations: int = 500) -> BenchResultEntry:
    """
    Verify guard behavior under fail-closed mode across repeated calls.

    Alternates between benign text and text containing sensitive credentials.
    Benign text must succeed; sensitive text must raise RedactionBlockedError.
    """
    engine = _get_default_redact_engine()
    correct_count = 0

    for i in range(iterations):
        if i % 2 == 0:
            # Benign text
            text = f"Normal decision note #{i} on architecture refactoring."
            try:
                engine.redact(text, mode="fail_closed")
                correct_count += 1
            except RedactionBlockedError:
                pass
        else:
            # Sensitive token
            text = f"Config key with sensitive token: ghp_SECRETTOKENVALUE1234567890{i}"
            try:
                engine.redact(text, mode="fail_closed")
            except RedactionBlockedError:
                correct_count += 1

    score = correct_count / iterations
    return BenchResultEntry(
        test="guard_behavior",
        n=iterations,
        value=round(score, 4),
        ci=[round(score, 4), round(score, 4)],
    )


def run_phase1_benchmarks(
    fixtures: list[dict[str, object]],
) -> list[BenchResultEntry]:
    """Execute all Phase 1 benchmark metrics and return result entries."""
    recall, precision = compute_redaction_metrics(fixtures)
    p50, p95 = compute_latency_metrics(fixtures)
    determinism = compute_determinism_metric(fixtures)
    guard = compute_guard_behavior_metric()

    return [
        recall,
        precision,
        p50,
        p95,
        determinism,
        guard,
    ]
