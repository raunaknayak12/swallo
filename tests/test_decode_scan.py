"""
Unit tests for decoded-variant scanning, decode-bomb defense, and opaque-blob detection.
"""

from __future__ import annotations

import base64
import binascii
import secrets

import pytest

from swallo.redact.decode import DecodedVariantDetector, OpaqueBlobDetector
from swallo.redact.patterns import PatternDetector


def test_decoded_variant_base64() -> None:
    inner = PatternDetector()
    detector = DecodedVariantDetector(inner_detectors=[inner])

    raw_secret = "ghp_111122223333444455556666777788889999"
    b64_secret = base64.b64encode(raw_secret.encode()).decode()

    text = f"Look at this payload: {b64_secret} in base64."
    findings = list(detector.scan(text))

    assert len(findings) == 1
    assert "encoded_github_token" in findings[0].kind
    assert findings[0].matched_text == b64_secret


def test_decoded_variant_hex() -> None:
    inner = PatternDetector()
    detector = DecodedVariantDetector(inner_detectors=[inner])

    raw_secret = "AKIA1234567890ABCDEF"
    hex_secret = binascii.hexlify(raw_secret.encode()).decode()

    text = f"Binary config: {hex_secret} in hex."
    findings = list(detector.scan(text))

    assert len(findings) == 1
    assert "encoded_aws_access_key" in findings[0].kind
    assert findings[0].matched_text == hex_secret


def test_decoded_variant_url() -> None:
    inner = PatternDetector()
    detector = DecodedVariantDetector(inner_detectors=[inner])

    raw_secret = "sk-1234567890abcdef1234567890abcdef1234"
    url_secret = "".join(f"%{ord(c):02x}" for c in raw_secret)

    text = f"Redirect target https://example.com/oauth?key={url_secret}"
    findings = list(detector.scan(text))

    assert len(findings) >= 1
    assert any("encoded_openai_api_key" in f.kind for f in findings)


def test_decoded_variant_zero_width_steganography() -> None:
    inner = PatternDetector()
    detector = DecodedVariantDetector(inner_detectors=[inner])

    raw_secret = "AKIA1234567890ABCDEF"
    # Convert ascii to binary using \u200b for '0' and \u200c for '1'
    zw_bits = "".join(f"{ord(c):08b}" for c in raw_secret)
    zw_text = "".join("\u200c" if b == "1" else "\u200b" for b in zw_bits)

    stego_message = f"Hello innocent user{zw_text} please proceed."
    findings = list(detector.scan(stego_message))

    assert len(findings) == 1
    assert "hidden_aws_access_key" in findings[0].kind


def test_decode_bomb_defense_bounded_time_and_size() -> None:
    inner = PatternDetector()
    # Set a tiny time limit to guarantee fast termination
    detector = DecodedVariantDetector(inner_detectors=[inner], time_limit=0.1)

    # Massive base64 string that expands or attempts denial of service
    bomb_text = base64.b64encode(b"A" * 100_000).decode() * 10
    findings = list(detector.scan(bomb_text))
    # Must complete safely without hanging or raising memory exceptions
    assert isinstance(findings, list)


def test_opaque_blob_detector() -> None:
    detector = OpaqueBlobDetector(min_length=60, min_entropy=4.5)

    # Long random token
    high_entropy_blob = secrets.token_urlsafe(70)
    text = f"We observed anomalous blob: {high_entropy_blob} in field."
    findings = list(detector.scan(text))

    assert len(findings) == 1
    assert findings[0].kind == "opaque_blob"
    assert findings[0].matched_text == high_entropy_blob

    # Normal text should NOT trigger opaque blob
    normal_text = "This is a standard English sentence of reasonable length describing software."
    assert list(detector.scan(normal_text)) == []


@pytest.mark.parametrize("prefix", ["-", "+", "/", "_", "a"])
@pytest.mark.parametrize("suffix", ["-", "+", "/", "_", "=", "z"])
def test_opaque_blob_boundary_characters(prefix: str, suffix: str) -> None:
    detector = OpaqueBlobDetector(min_length=60, min_entropy=4.5)
    middle = secrets.token_urlsafe(60)
    blob = f"{prefix}{middle}{suffix}"
    text = f"Payload: {blob} end."
    findings = list(detector.scan(text))
    assert len(findings) == 1
    assert findings[0].matched_text == blob
