"""Text normalization and canonical hashing for packet item deduplication.

Normalization is used **only** for comparison purposes — the original text
is always preserved.  The pipeline is:

1. Unicode NFC normalization (compose canonical equivalents)
2. Whitespace collapse (all runs of whitespace → single space, then strip)
3. Lowercase (case-insensitive comparison)
4. Punctuation stripping (ASCII punctuation removed for fuzzy matching)

``normalized_hash`` returns the SHA-256 hex digest of the normalized text
encoded as UTF-8.  Two items with the same hash are considered exact
duplicates for deduplication purposes.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r"\s+")
_PUNCTUATION_RE = re.compile(r"[^\w\s]", re.UNICODE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize_text(text: str) -> str:
    """Return a normalized, comparison-only form of *text*.

    The original *text* is never modified; the return value is used solely
    for hashing and similarity comparison.

    Args:
        text: The raw string to normalize.

    Returns:
        A lowercase, whitespace-collapsed, punctuation-stripped, NFC-composed
        version of *text*.
    """
    # 1. Unicode NFC composition
    nfc = unicodedata.normalize("NFC", text)
    # 2. Lowercase
    lower = nfc.lower()
    # 3. Remove punctuation (keep word chars and whitespace)
    no_punct = _PUNCTUATION_RE.sub(" ", lower)
    # 4. Collapse whitespace and strip
    collapsed = _WHITESPACE_RE.sub(" ", no_punct).strip()
    return collapsed


def normalized_hash(text: str) -> str:
    """Return the SHA-256 hex digest of the normalized form of *text*.

    Two strings that differ only in case, punctuation, or whitespace will
    produce the same hash and are therefore considered exact duplicates.

    Args:
        text: The raw string to hash.

    Returns:
        A 64-character lowercase hex string (SHA-256 digest).
    """
    normalized = normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
