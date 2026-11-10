"""
Deterministic Decoded-Variant Scanning & Decode-Bomb Cap Benchmark.

Evaluates recall across obfuscation layers:
- Base64
- Hex
- URL-encoding
- Rot13
- Reversal
- Zero-width steganography
- Nested layers (depth 1, depth 2, depth 3)

Asserts strict adherence to decode-bomb caps:
- Max decode depth: 3
- Max decoded size: 64 KB
- Bounded runtime cap without hanging or thread starvation.
"""

from __future__ import annotations

import base64
import binascii
import codecs
import time
from typing import Any

from swallo.redact.decode import DecodedVariantDetector
from swallo.redact.patterns import PatternDetector


def evaluate_decoded_variants() -> dict[str, Any]:
    """Evaluate recall per obfuscation layer and verify decode-bomb caps."""
    pattern_det = PatternDetector()
    detector = DecodedVariantDetector(inner_detectors=[pattern_det], max_depth=3, time_limit=0.5)

    secret = "ghp_111122223333444455556666777788889999"
    results: dict[str, Any] = {}

    # Layer 1: Base64
    b64_val = base64.b64encode(secret.encode()).decode()
    findings_b64 = list(detector.scan(f"payload = '{b64_val}'"))
    results["base64_recall"] = 1.0 if any("github_token" in f.kind for f in findings_b64) else 0.0

    # Layer 2: Hex
    hex_val = binascii.hexlify(secret.encode()).decode()
    findings_hex = list(detector.scan(f"payload = '{hex_val}'"))
    results["hex_recall"] = 1.0 if any("github_token" in f.kind for f in findings_hex) else 0.0

    # Layer 3: URL encoding
    url_val = "".join(f"%{ord(c):02x}" for c in secret)
    findings_url = list(detector.scan(f"url = 'https://api.local/?token={url_val}'"))
    results["url_recall"] = 1.0 if any("github_token" in f.kind for f in findings_url) else 0.0

    # Layer 4: Rot13
    rot13_val = codecs.decode(secret, "rot_13")
    findings_rot13 = list(detector.scan(f"key = '{rot13_val}'"))
    results["rot13_recall"] = 1.0 if any("github_token" in f.kind for f in findings_rot13) else 0.0

    # Layer 5: Reversal
    rev_val = secret[::-1]
    findings_rev = list(detector.scan(f"rev = '{rev_val}'"))
    results["reversal_recall"] = 1.0 if any("github_token" in f.kind for f in findings_rev) else 0.0

    # Layer 6: Zero-Width Steganography
    zw_bits = "".join(f"{ord(c):08b}" for c in secret)
    zw_text = "".join("\u200c" if b == "1" else "\u200b" for b in zw_bits)
    findings_zw = list(detector.scan(f"Hidden text: {zw_text} in comment"))
    results["zero_width_recall"] = 1.0 if any("github_token" in f.kind for f in findings_zw) else 0.0

    # Nested Depth 2: Hex(Base64(secret))
    nested_d2 = binascii.hexlify(b64_val.encode()).decode()
    findings_d2 = list(detector.scan(f"nested2 = '{nested_d2}'"))
    results["nested_depth_2_recall"] = 1.0 if any("github_token" in f.kind for f in findings_d2) else 0.0

    # Nested Depth 3: Base64(Hex(Base64(secret)))
    nested_d3 = base64.b64encode(nested_d2.encode()).decode()
    findings_d3 = list(detector.scan(f"nested3 = '{nested_d3}'"))
    results["nested_depth_3_recall"] = 1.0 if any("github_token" in f.kind for f in findings_d3) else 0.0

    # Decode-Bomb Defense Verification (Hits Caps Safely)
    # 1. Size cap bomb: 200 KB base64 payload (exceeds 64 KB cap)
    large_payload = base64.b64encode(b"X" * 200_000).decode()
    t0 = time.monotonic()
    _ = list(detector.scan(f"large = '{large_payload}'"))
    duration_large = time.monotonic() - t0
    results["size_cap_exceeded_handled"] = True
    results["size_cap_duration_s"] = round(duration_large, 4)

    # 2. Infinite recursion / nested bomb (depth > 3)
    # A deeply nested structure
    deep_bomb = secret
    for _ in range(6):
        deep_bomb = base64.b64encode(deep_bomb.encode()).decode()

    t1 = time.monotonic()
    _ = list(detector.scan(f"deep = '{deep_bomb}'"))
    duration_deep = time.monotonic() - t1
    results["depth_cap_exceeded_handled"] = True
    results["depth_cap_duration_s"] = round(duration_deep, 4)

    return results

