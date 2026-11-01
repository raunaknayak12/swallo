"""
Unit tests for the redaction engine and keyed placeholder generation.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterable

import pytest

from swallo.errors import RedactionBlockedError
from swallo.redact.engine import Finding, RedactionEngine, make_keyed_placeholder


class StubDetector:
    """Mock detector for testing engine orchestration."""

    name = "stub_detector"

    def __init__(self, targets: list[tuple[str, str]]) -> None:
        self.targets = targets  # list of (kind, exact_substring)

    def scan(self, text: str) -> Iterable[Finding]:
        for kind, target in self.targets:
            start = 0
            while True:
                idx = text.find(target, start)
                if idx == -1:
                    break
                yield Finding(
                    detector=self.name,
                    kind=kind,
                    start=idx,
                    end=idx + len(target),
                    matched_text=target,
                )
                start = idx + 1


def test_make_keyed_placeholder() -> None:
    key1 = secrets.token_bytes(32)
    key2 = secrets.token_bytes(32)
    secret = "sk-live-supersecretpassword123"

    p1 = make_keyed_placeholder(key1, "api_key", secret)
    assert p1.startswith("[REDACTED:API_KEY:")
    assert p1.endswith("]")
    assert len(p1.split(":")[-1].rstrip("]")) == 8

    # Same key and secret produces deterministic placeholder
    assert make_keyed_placeholder(key1, "api_key", secret) == p1

    # Different key produces different hash
    p2 = make_keyed_placeholder(key2, "api_key", secret)
    assert p2 != p1


def test_redact_engine_clean_text() -> None:
    engine = RedactionEngine()
    result = engine.redact("Clean input text with no secrets.")
    assert result.text == "Clean input text with no secrets."
    assert result.findings == []
    assert result.redacted_count == 0


def test_redact_fail_closed_mode() -> None:
    detector = StubDetector([("api_key", "secret_token_123")])
    engine = RedactionEngine([detector])

    text = "Authorization: Bearer secret_token_123 in headers"
    with pytest.raises(RedactionBlockedError, match="Redaction blocked save: 1 sensitive"):
        engine.redact(text, mode="fail_closed")


def test_redact_warn_mode_replacement() -> None:
    detector = StubDetector([("api_key", "secret_token_123")])
    engine = RedactionEngine([detector])
    key = secrets.token_bytes(32)

    text = "Key: secret_token_123 end"
    result = engine.redact(text, mode="warn", key=key)

    assert result.redacted_count == 1
    assert "secret_token_123" not in result.text
    assert "[REDACTED:API_KEY:" in result.text
    assert result.text.startswith("Key: [REDACTED:API_KEY:")
    assert result.text.endswith(" end")


def test_redact_handles_overlapping_matches() -> None:
    # Outer match: "super_secret_token"
    # Inner match: "secret"
    d1 = StubDetector([("token", "super_secret_token")])
    d2 = StubDetector([("keyword", "secret")])
    engine = RedactionEngine([d1, d2])

    text = "value = super_secret_token;"
    result = engine.redact(text, mode="warn")

    # The longer match should take precedence, no duplicate corrupted replacements
    assert result.redacted_count == 1
    assert "super_secret_token" not in result.text
    assert "[REDACTED:TOKEN:" in result.text
