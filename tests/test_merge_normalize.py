"""Tests for swallo.merge.normalize — text normalization and canonical hashing."""

from __future__ import annotations

import pytest

from swallo.merge.normalize import normalize_text, normalized_hash


class TestNormalizeText:
    def test_whitespace_collapse(self) -> None:
        assert normalize_text("hello   world") == "hello world"

    def test_leading_trailing_strip(self) -> None:
        assert normalize_text("  hello  ") == "hello"

    def test_newlines_collapsed(self) -> None:
        assert normalize_text("hello\nworld") == "hello world"

    def test_tabs_collapsed(self) -> None:
        assert normalize_text("hello\t\tworld") == "hello world"

    def test_lowercase(self) -> None:
        assert normalize_text("Hello World") == "hello world"

    def test_punctuation_stripped(self) -> None:
        # Punctuation is replaced with spaces, then collapsed
        assert normalize_text("hello, world!") == "hello world"

    def test_unicode_nfc(self) -> None:
        # Composed form (single codepoint) and decomposed form (base + combining)
        # should normalize to the same string.
        composed = "\u00e9"  # é as single codepoint
        decomposed = "e\u0301"  # e + combining acute accent
        assert normalize_text(composed) == normalize_text(decomposed)

    def test_empty_string(self) -> None:
        assert normalize_text("") == ""

    def test_all_punctuation(self) -> None:
        assert normalize_text("!!!???...") == ""

    def test_mixed_case_unicode(self) -> None:
        assert normalize_text("Ñoño") == "ñoño"


class TestNormalizedHash:
    def test_same_hash_for_equivalent_text(self) -> None:
        # Differ only in case, punctuation, and whitespace → same hash
        assert normalized_hash("Hello, World!") == normalized_hash("hello world")

    def test_different_text_different_hash(self) -> None:
        assert normalized_hash("hello world") != normalized_hash("goodbye world")

    def test_hash_is_hex_string(self) -> None:
        digest = normalized_hash("test")
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_case_insensitive(self) -> None:
        assert normalized_hash("Hello") == normalized_hash("hello")

    def test_whitespace_insensitive(self) -> None:
        assert normalized_hash("a b c") == normalized_hash("a  b  c")

    def test_unicode_nfc_dedup(self) -> None:
        composed = "\u00e9l\u00e8ve"  # élève
        decomposed = "e\u0301le\u0300ve"  # élève in decomposed form
        assert normalized_hash(composed) == normalized_hash(decomposed)

    def test_empty_string(self) -> None:
        # Deterministic — same hash every time for empty input
        h1 = normalized_hash("")
        h2 = normalized_hash("")
        assert h1 == h2

    def test_deterministic(self) -> None:
        text = "The quick brown fox jumps over the lazy dog"
        assert normalized_hash(text) == normalized_hash(text)


@pytest.mark.parametrize(
    "a,b",
    [
        ("Hello, World!", "hello world"),
        ("  spaces  ", "spaces"),
        ("line1\nline2", "line1 line2"),
        ("\u00e9", "e\u0301"),  # NFC equivalence
    ],
)
def test_same_hash_parametrized(a: str, b: str) -> None:
    """Pairs of text that differ only in normalization-sensitive ways share a hash."""
    assert normalized_hash(a) == normalized_hash(b)
