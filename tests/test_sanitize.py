"""
Unit and property tests for text sanitization and invisible character flagging.
"""

from __future__ import annotations

from swallo.render.sanitize import flag_invisible, sanitize_for_display


def test_sanitize_clean_text() -> None:
    text = "Hello, world! This is clean text with numbers 1234."
    assert sanitize_for_display(text) == text


def test_sanitize_preserves_allowed_whitespace() -> None:
    text = "Line 1\nLine 2\r\n\tIndented line"
    assert sanitize_for_display(text) == text


def test_sanitize_strips_ansi_escapes() -> None:
    text = "\x1b[31;1mRed Bold Text\x1b[0m and \x1b[2JClear Screen"
    assert sanitize_for_display(text) == "Red Bold Text and Clear Screen"


def test_sanitize_strips_tag_characters() -> None:
    # Tag Latin small letter a: U+E0061
    text = "Secret\U000E0061\U000E0062Payload"
    assert sanitize_for_display(text) == "SecretPayload"


def test_sanitize_strips_bidi_controls() -> None:
    # Right-to-Left Override: U+202E, Left-to-Right Embedding: U+202A
    text = "Harmless\u202eEXE.DOC\u202c"
    assert sanitize_for_display(text) == "HarmlessEXE.DOC"


def test_sanitize_strips_control_characters() -> None:
    # Bell \x07, Backspace \x08, Form feed \x0c
    text = "A\x07B\x08C\x0c"
    assert sanitize_for_display(text) == "ABC"


def test_sanitize_max_len_truncation() -> None:
    text = "abcdefghij"
    assert sanitize_for_display(text, max_len=6) == "abc..."
    assert sanitize_for_display(text, max_len=2) == "ab"
    assert sanitize_for_display(text, max_len=10) == "abcdefghij"
    assert sanitize_for_display("", max_len=10) == ""


def test_flag_invisible_detects_zero_width_characters() -> None:
    # Persian text with legitimate ZWNJ (U+200C)
    text = "می\u200cخواهم"
    flags = flag_invisible(text)
    assert len(flags) == 1
    assert "U+200C" in flags[0]
    assert "ZERO WIDTH NON-JOINER" in flags[0]


def test_flag_invisible_clean_text() -> None:
    assert flag_invisible("Regular English sentence without hidden characters.") == []
    assert flag_invisible("") == []


def test_flag_invisible_multiple_occurrences() -> None:
    text = "A\u200bB\ufeffC\u200dD"
    flags = flag_invisible(text)
    assert len(flags) == 3
    assert any("U+200B" in f for f in flags)
    assert any("U+FEFF" in f for f in flags)
    assert any("U+200D" in f for f in flags)
