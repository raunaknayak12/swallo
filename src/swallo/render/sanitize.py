"""
Text sanitization and invisible character inspection for swallo.

Per TRD.md section 6.5, IMPLEMENTATION_PLAN.md Step 3, and ADR-021:
- Strips ANSI escape sequences and terminal control characters.
- Strips Unicode tag characters (U+E0000 to U+E007F).
- Strips Unicode bidirectional overrides and embedding controls (U+202A..U+202E, U+2066..U+2069).
- Truncates safely for terminal display with max_len constraint.
- Flags (without stripping) invisible format characters like zero-width spaces and joiners
  for risk review.
"""

from __future__ import annotations

import re

# Matches ANSI escape sequences: CSI sequences, OSC sequences, and 2-byte escape codes
_ANSI_ESCAPE_RE = re.compile(
    r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\].*?(?:\x07|\x1b\\))"
)

# Unicode tag characters: U+E0000 to U+E007F
_TAG_CHARS_RE = re.compile(r"[\U000E0000-\U000E007F]")

# Unicode bidirectional control characters to strip:
# U+202A (LRE), U+202B (RLE), U+202C (PDF), U+202D (LRO), U+202E (RLO)
# U+2066 (LRI), U+2067 (RLI), U+2068 (FSI), U+2069 (PDI)
# Also include U+061C (Arabic Letter Mark)
_BIDI_CONTROLS_RE = re.compile(r"[\u202A-\u202E\u2066-\u2069\u061C]")

# Characters flagged as invisible / zero-width for human review in risk summaries
_INVISIBLE_CODEPOINTS: dict[int, str] = {
    0x00AD: "SOFT HYPHEN",
    0x200B: "ZERO WIDTH SPACE",
    0x200C: "ZERO WIDTH NON-JOINER",
    0x200D: "ZERO WIDTH JOINER",
    0x200E: "LEFT-TO-RIGHT MARK",
    0x200F: "RIGHT-TO-LEFT MARK",
    0x2060: "WORD JOINER",
    0x2061: "FUNCTION APPLICATION",
    0x2062: "INVISIBLE TIMES",
    0x2063: "INVISIBLE SEPARATOR",
    0x2064: "INVISIBLE PLUS",
    0xFEFF: "ZERO WIDTH NO-BREAK SPACE",
}


def sanitize_for_display(text: str, max_len: int = 2000) -> str:
    """
    Sanitize untrusted text before displaying or rendering in terminals or markdown.

    - Strips ANSI escape sequences.
    - Strips Unicode tag characters and bidi overrides/embeddings.
    - Strips C0 and C1 control characters (except newline, carriage return, and tab).
    - Caps output length to max_len.
    """
    if not text:
        return ""

    # 1. Strip ANSI escape sequences
    cleaned = _ANSI_ESCAPE_RE.sub("", text)

    # 2. Strip Unicode tag characters
    cleaned = _TAG_CHARS_RE.sub("", cleaned)

    # 3. Strip Bidi overrides and embedding controls
    cleaned = _BIDI_CONTROLS_RE.sub("", cleaned)

    # 4. Strip control characters except newline (\n), carriage return (\r), and tab (\t)
    out_chars: list[str] = []
    for ch in cleaned:
        code = ord(ch)
        if code in (9, 10, 13):  # \t, \n, \r
            out_chars.append(ch)
        elif code < 32 or (127 <= code <= 159):
            # ASCII control or C1 control character
            continue
        else:
            out_chars.append(ch)

    sanitized = "".join(out_chars)

    # 5. Length cap
    if len(sanitized) > max_len:
        if max_len >= 3:
            return sanitized[: max_len - 3] + "..."
        return sanitized[:max_len]

    return sanitized


def flag_invisible(text: str) -> list[str]:
    """
    Scan text and report zero-width or invisible format characters without stripping them.

    These are flagged in the risk summary because some languages (e.g. Persian, Devanagari)
    require zero-width joiners for legitimate typography, while hidden text can be used
    for prompt injection or steganography.
    """
    if not text:
        return []

    flags: list[str] = []
    for idx, ch in enumerate(text):
        code = ord(ch)
        if code in _INVISIBLE_CODEPOINTS:
            name = _INVISIBLE_CODEPOINTS[code]
            flags.append(f"U+{code:04X} ({name}) at offset {idx}")

    return flags
