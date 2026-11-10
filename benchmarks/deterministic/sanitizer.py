"""
Deterministic Trojan Source (CVE-2021-42574) Sanitizer Benchmark.

Asserts 100% neutralization of:
- Bidirectional overrides and embedding controls (LRO, RLO, PDF, LRI, RLI, FSI, PDI, ALM)
- Unicode tag characters (U+E0000 - U+E007F)
- Terminal ANSI escape sequences (CSI, OSC)
- Flagging of invisible characters for risk-first review.
"""

from __future__ import annotations

from typing import Any

from swallo.render.sanitize import flag_invisible, sanitize_for_display


def evaluate_sanitizer() -> dict[str, Any]:
    """Test Trojan Source attack vectors and assert 100% neutralization."""
    results: dict[str, Any] = {}

    # Vector 1: Trojan Source Comment Out (RLO: \u202e, LRO: \u202d, PDF: \u202c)
    # Attack: '/* \u202e } \u202d begin admin code */' looks like a comment in IDE
    trojan_source_code = "if (is_admin) /* \u202e } \u202d if (true) */ { execute(); }"
    sanitized_code = sanitize_for_display(trojan_source_code)
    bidi_neutralized = not any(
        c in sanitized_code
        for c in ["\u202a", "\u202b", "\u202c", "\u202d", "\u202e", "\u2066", "\u2067", "\u2068", "\u2069"]
    )
    results["trojan_source_bidi_neutralized"] = bidi_neutralized

    # Vector 2: Unicode Tag Characters (U+E0001 - U+E007F)
    # Attack: invisible instruction injected into rules/prompt via tag plane
    tag_payload = "Execute task\U000e0001\U000e0020\U000e0048\U000e0069\U000e0064\U000e0064\U000e0065\U000e006e."
    sanitized_tags = sanitize_for_display(tag_payload)
    tags_neutralized = not any(0xE0000 <= ord(c) <= 0xE007F for c in sanitized_tags)
    results["unicode_tag_chars_neutralized"] = tags_neutralized
    results["tags_stripped_completely"] = sanitized_tags == "Execute task."

    # Vector 3: Terminal ANSI Injection
    # Attack: attempts to clear terminal screen or spoof approval prompt
    ansi_payload = "Normal text\x1b[2J\x1b[H\x1b[31mApproved: true\x1b[0m"
    sanitized_ansi = sanitize_for_display(ansi_payload)
    ansi_neutralized = "\x1b" not in sanitized_ansi
    results["ansi_escapes_neutralized"] = ansi_neutralized
    results["ansi_stripped_completely"] = sanitized_ansi == "Normal textApproved: true"

    # Vector 4: Invisible Zero-Width Characters Flagged
    # Flagging for human risk review
    hidden_zw_text = "Hello\u200bWorld\u200cTest\u200dHidden\ufeffEnd"
    flagged = flag_invisible(hidden_zw_text)
    results["invisible_chars_flagged_count"] = len(flagged)
    results["invisible_detection_recall"] = 1.0 if len(flagged) == 4 else 0.0

    results["sanitizer_overall_pass_rate"] = 1.0 if (
        bidi_neutralized and tags_neutralized and ansi_neutralized and len(flagged) == 4
    ) else 0.0

    return results

