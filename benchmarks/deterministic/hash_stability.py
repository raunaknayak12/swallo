"""
Deterministic Canonical Hash Stability & Invariant Benchmark.

Per ADR-024 and PACKET_SCHEMA.md:
- Key order invariance (lexicographically sorted UTF-8 keys).
- Unicode NFC normalization across equivalent representations.
- Exclusion of volatile fields ('id', 'created_at', 'captured_at') from hashed representation.
- Float, NaN, and Infinity rejection anywhere in the packet.
- Integer boundaries: strictly within +/-(2^53 - 1) [9007199254740991].
"""

from __future__ import annotations

import unicodedata
from typing import Any

from swallo.errors import ValidationError as SwalloValidationError
from swallo.schema.canonical import canonicalize, packet_hash
from swallo.schema.models import Goal, Item, Packet, Source


def _make_source(session_id: str = "bench_session", captured_at: str = "2026-01-01T00:00:00Z") -> Source:
    """Build a minimal valid Source object using all required fields."""
    return Source(
        session_id=session_id,
        agent="bench_agent",
        capture_method="paste",
        captured_at=captured_at,
    )


def evaluate_hash_stability() -> dict[str, Any]:
    """Test and assert canonical hash stability and invariance properties."""
    results: dict[str, Any] = {}

    # 1. Key Order Invariance
    dict_a = {"z_field": 100, "a_field": "hello", "m_field": [3, 2, 1]}
    dict_b = {"a_field": "hello", "m_field": [3, 2, 1], "z_field": 100}
    c_a = canonicalize(dict_a)
    c_b = canonicalize(dict_b)
    results["key_order_invariance"] = c_a == c_b

    # 2. Unicode NFC Normalization
    # 'café' in NFC (precomposed é: \u00e9) vs NFD (e + combining acute: e\u0301)
    nfc_str = "caf\u00e9"
    nfd_str = unicodedata.normalize("NFD", nfc_str)
    c_nfc = canonicalize({"name": nfc_str})
    c_nfd = canonicalize({"name": nfd_str})
    results["unicode_nfc_normalization"] = c_nfc == c_nfd

    # 3. Volatile Fields Exclusion
    # pkt1 and pkt2 differ only in id, created_at, and captured_at — hash must be equal.
    pkt1 = Packet(
        id="pkt_111111111111",
        schema_version="0.1",
        created_at="2026-01-01T00:00:00Z",
        project="bench_proj",
        goal=Goal(text="test goal"),
        sources=[_make_source(captured_at="2026-01-01T00:00:00Z")],
        items=[Item(id="it_11111111", kind="decision", text="Decision 1")],
    )
    pkt2 = Packet(
        id="pkt_222222222222",
        schema_version="0.1",
        created_at="2026-11-10T23:59:59Z",
        project="bench_proj",
        goal=Goal(text="test goal"),
        sources=[_make_source(captured_at="2026-11-10T23:59:59Z")],
        items=[Item(id="it_11111111", kind="decision", text="Decision 1")],
    )
    hash1 = packet_hash(pkt1.model_dump())
    hash2 = packet_hash(pkt2.model_dump())
    results["volatile_fields_excluded"] = hash1 == hash2

    # 4. Float / NaN / Infinity Rejection
    # canonicalize() raises swallo.errors.ValidationError (a subclass of Exception)
    float_rejected = False
    try:
        canonicalize({"score": 9.5})
    except SwalloValidationError:
        float_rejected = True
    results["float_rejected"] = float_rejected

    nan_rejected = False
    try:
        canonicalize({"score": float("nan")})
    except SwalloValidationError:
        nan_rejected = True
    results["nan_rejected"] = nan_rejected

    inf_rejected = False
    try:
        canonicalize({"score": float("inf")})
    except SwalloValidationError:
        inf_rejected = True
    results["inf_rejected"] = inf_rejected

    # 5. Integer Boundaries: ±(2^53 - 1) = 9007199254740991
    max_safe_int = 9007199254740991
    min_safe_int = -9007199254740991

    # Within bounds should pass
    in_bound_pass = False
    try:
        c_max = canonicalize({"val": max_safe_int})
        c_min = canonicalize({"val": min_safe_int})
        in_bound_pass = bool(c_max and c_min)
    except SwalloValidationError:
        in_bound_pass = False
    results["safe_int_boundary_accepted"] = in_bound_pass

    # Exceeding bounds should fail
    exceeded_rejected = False
    try:
        canonicalize({"val": max_safe_int + 1})
    except SwalloValidationError:
        exceeded_rejected = True
    results["exceeded_int_boundary_rejected"] = exceeded_rejected

    return results
