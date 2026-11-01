"""
High-confidence regex secret detector for swallo.

Per TRD.md section 6.2 and IMPLEMENTATION_PLAN.md Step 3:
- Targets cloud provider keys (AWS, GitHub, OpenAI, Anthropic, Slack).
- Targets private keys (PEM format RSA, EC, OpenSSH, DSA).
- Targets authorization bearer tokens and connection string passwords.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from swallo.redact.engine import Finding

_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "aws_access_key",
        re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
    ),
    (
        "github_token",
        re.compile(r"\b(gh[pousr]_[A-Za-z0-9_]{36,255}|github_pat_[A-Za-z0-9_]{82})\b"),
    ),
    (
        "openai_api_key",
        re.compile(r"\b(sk-(?!ant-)(?:proj-)?[A-Za-z0-9_-]{32,120})\b"),
    ),
    (
        "anthropic_api_key",
        re.compile(r"\b(sk-ant-[A-Za-z0-9_-]{32,120})\b"),
    ),
    (
        "slack_token",
        re.compile(r"\b(xox[baprs]-[0-9A-Za-z-]{10,72})\b"),
    ),
    (
        "private_key",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
            r"[\s\S]+?"
            r"-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
        ),
    ),
    (
        "bearer_token",
        re.compile(r"(?i)\bbearer\s+([a-zA-Z0-9_\-\.]{24,})\b"),
    ),
    (
        "connection_password",
        re.compile(r"(?i)\b(?:password|passwd|pwd)\s*[:=]\s*['\"]([^'\"]{6,})['\"]"),
    ),
]


class PatternDetector:
    """Detects secrets matching known high-confidence regular expressions."""

    name = "pattern_detector"

    def __init__(self, patterns: list[tuple[str, re.Pattern[str]]] | None = None) -> None:
        self.patterns = list(patterns) if patterns else list(_SECRET_PATTERNS)

    def scan(self, text: str) -> Iterable[Finding]:
        if not text:
            return

        for kind, pat in self.patterns:
            for match in pat.finditer(text):
                # If pattern has a capturing group, match against that group; otherwise full match
                if match.groups():
                    matched_str = match.group(1)
                    start, end = match.start(1), match.end(1)
                else:
                    matched_str = match.group(0)
                    start, end = match.start(0), match.end(0)

                yield Finding(
                    detector=self.name,
                    kind=kind,
                    start=start,
                    end=end,
                    matched_text=matched_str,
                    severity="high",
                )
