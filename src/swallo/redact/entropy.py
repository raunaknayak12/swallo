"""
Shannon entropy secret detector for swallo.

Per TRD.md section 6.2 and IMPLEMENTATION_PLAN.md Step 3:
- Flags unformatted, high-entropy tokens (e.g. raw secret keys, randomly generated passwords).
- Computes Shannon entropy over alphanumeric and base64-like words >= 20 characters.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable

from swallo.redact.engine import Finding

_WORD_TOKEN_RE = re.compile(r"\b[A-Za-z0-9+/=_-]{20,}\b")


def shannon_entropy(s: str) -> float:
    """Compute Shannon entropy in bits per character for string s."""
    if not s:
        return 0.0

    counts = Counter(s)
    total = len(s)
    entropy = 0.0
    for count in counts.values():
        p = count / total
        entropy -= p * math.log2(p)
    return entropy


class EntropyDetector:
    """Scans for high-entropy strings exceeding a Shannon entropy threshold."""

    name = "entropy_detector"

    def __init__(self, threshold: float = 4.3, min_length: int = 20) -> None:
        self.threshold = threshold
        self.min_length = min_length

    def scan(self, text: str) -> Iterable[Finding]:
        if not text:
            return

        for match in _WORD_TOKEN_RE.finditer(text):
            token = match.group(0)
            if len(token) < self.min_length:
                continue

            # Calculate Shannon entropy
            ent = shannon_entropy(token)
            if ent >= self.threshold:
                yield Finding(
                    detector=self.name,
                    kind="high_entropy_secret",
                    start=match.start(),
                    end=match.end(),
                    matched_text=token,
                    severity="high" if ent >= 4.8 else "medium",
                )

