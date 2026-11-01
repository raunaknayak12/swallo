"""
User-defined denylist detector for swallo.

Per TRD.md section 6.2 and IMPLEMENTATION_PLAN.md Step 3:
- Matches user-specified sensitive terms, codenames, project internal names,
  or known proprietary credentials.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from swallo.redact.engine import Finding


class DenylistDetector:
    """Detects occurrences of terms specified in a configured denylist."""

    name = "denylist_detector"

    def __init__(self, terms: list[str] | None = None, case_sensitive: bool = False) -> None:
        self.terms = [t.strip() for t in (terms or []) if t.strip()]
        self.case_sensitive = case_sensitive

    def scan(self, text: str) -> Iterable[Finding]:
        if not text or not self.terms:
            return

        flags = 0 if self.case_sensitive else re.IGNORECASE
        for term in self.terms:
            escaped = re.escape(term)
            pattern = re.compile(rf"\b{escaped}\b", flags)
            for m in pattern.finditer(text):
                yield Finding(
                    detector=self.name,
                    kind="denylist_term",
                    start=m.start(),
                    end=m.end(),
                    matched_text=m.group(0),
                    severity="high",
                )
