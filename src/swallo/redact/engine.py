"""
Core redaction engine, detector protocol, and keyed placeholder replacements.

Per TRD.md section 6.2, IMPLEMENTATION_PLAN.md Step 3, and Security.md F5:
- Defines Detector protocol for pluggable detectors (regex patterns, entropy, denylist).
- Computes keyed deterministic placeholders:
    [REDACTED:<kind>:<keyed-short-hash>]
  where <keyed-short-hash> is the first 8 hex characters of HMAC-SHA256(key, secret).
- Supports two modes:
  - "fail_closed": Raises RedactionBlockedError if any findings exist.
  - "warn": Replaces sensitive spans with keyed placeholders.
- Gracefully handles overlapping finding spans by prioritizing larger non-overlapping matches.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, Protocol

from swallo.errors import RedactionBlockedError


@dataclass(frozen=True)
class Finding:
    """Represents a secret, credential, or sensitive finding identified in text."""

    detector: str
    kind: str
    start: int
    end: int
    matched_text: str
    severity: Literal["high", "medium", "low"] = "high"


@dataclass(frozen=True)
class RedactionResult:
    """Outcome of running the redaction pipeline on a block of text."""

    text: str
    findings: list[Finding]
    redacted_count: int


class Detector(Protocol):
    """Protocol for all swallo secret and credential scanning detectors."""

    name: str

    def scan(self, text: str) -> Iterable[Finding]:
        """Scan input text and yield identified findings."""
        ...


def make_keyed_placeholder(key: bytes, kind: str, secret: str) -> str:
    """
    Generate a keyed placeholder: [REDACTED:<kind>:<short_hash>].

    The keyed hash is HMAC-SHA256(key, secret)[:8], allowing audit correlation
    without exposing secret material.
    """
    short_hash = hmac.new(key, secret.encode("utf-8"), hashlib.sha256).hexdigest()[:8]
    clean_kind = kind.upper().replace(" ", "_")
    return f"[REDACTED:{clean_kind}:{short_hash}]"


class RedactionEngine:
    """Orchestrates detectors and applies redactions to text."""

    def __init__(self, detectors: list[Detector] | None = None) -> None:
        self.detectors = list(detectors) if detectors else []

    def add_detector(self, detector: Detector) -> None:
        """Register a new detector instance."""
        self.detectors.append(detector)

    def scan(self, text: str) -> list[Finding]:
        """Run all registered detectors and return deduplicated findings sorted by offset."""
        if not text:
            return []

        all_findings: list[Finding] = []
        for det in self.detectors:
            all_findings.extend(det.scan(text))

        # Sort primarily by start offset ascending, then by match length descending
        all_findings.sort(key=lambda f: (f.start, -(f.end - f.start)))
        return all_findings

    def redact(
        self,
        text: str,
        mode: Literal["fail_closed", "warn"] = "warn",
        key: bytes | None = None,
    ) -> RedactionResult:
        """
        Execute scan and apply redaction according to the specified policy mode.

        Args:
            text: Raw input text.
            mode: "fail_closed" (raise RedactionBlockedError) or "warn" (replace with placeholders).
            key: 32-byte store key for keyed placeholders. If None, uses a zero dummy key.

        Raises:
            RedactionBlockedError: If mode is "fail_closed" and findings are found.
        """
        if not text:
            return RedactionResult(text="", findings=[], redacted_count=0)

        findings = self.scan(text)
        if not findings:
            return RedactionResult(text=text, findings=[], redacted_count=0)

        if mode == "fail_closed":
            raise RedactionBlockedError(
                f"Redaction blocked save: {len(findings)} sensitive pattern(s) detected "
                "in fail-closed mode."
            )

        active_key = key if key is not None else b"\x00" * 32

        # Non-overlapping replacement
        # Filter findings to eliminate overlapping intervals
        non_overlapping: list[Finding] = []
        last_end = -1
        for f in findings:
            if f.start >= last_end:
                non_overlapping.append(f)
                last_end = f.end

        # Reconstruct text with placeholders
        chunks: list[str] = []
        curr_idx = 0
        for f in non_overlapping:
            chunks.append(text[curr_idx : f.start])
            placeholder = make_keyed_placeholder(active_key, f.kind, f.matched_text)
            chunks.append(placeholder)
            curr_idx = f.end
        chunks.append(text[curr_idx:])

        redacted_text = "".join(chunks)
        return RedactionResult(
            text=redacted_text,
            findings=findings,
            redacted_count=len(non_overlapping),
        )

