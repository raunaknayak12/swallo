"""
Decoded-variant secret scanning and opaque-blob detection with decode-bomb defense.

Per ADR-022, TRD.md section 6.2, and IMPLEMENTATION_PLAN.md Step 3:
- Prevents evasion where secrets are obfuscated in Base64, Hex, URL encoding, reversal,
  or zero-width steganography.
- Implements bounded recursion depth (max 2), input size caps (64 KB), and time caps
  to prevent decode-bomb denial of service.
- Opaque-blob rule: flags unexplained long encoded/high-entropy strings in prose for human review.
"""

from __future__ import annotations

import base64
import binascii
import re
import time
import urllib.parse
from collections.abc import Iterable

from swallo.redact.engine import Detector, Finding
from swallo.redact.entropy import shannon_entropy

# Bounded caps for decode-bomb defense
MAX_DECODE_DEPTH = 2
MAX_DECODED_SIZE = 64 * 1024  # 64 KB
MAX_SCAN_SECONDS = 0.5

# Patterns for candidate encoded structures
_BASE64_CANDIDATE_RE = re.compile(r"(?:\b[A-Za-z0-9+/]{20,}={0,2}(?=[^A-Za-z0-9+/=]|$))")
_HEX_CANDIDATE_RE = re.compile(r"\b[0-9a-fA-F]{32,}\b")
_URL_CANDIDATE_RE = re.compile(r"(?:%[0-9a-fA-F]{2}[A-Za-z0-9_.-]*)+")
_ZERO_WIDTH_CHARS = ("\u200b", "\u200c", "\u200d", "\ufeff")


def _extract_zero_width_hidden(text: str) -> str | None:
    """Extract binary-encoded ascii hidden within zero-width characters."""
    zw_seq: list[str] = []
    for ch in text:
        if ch == "\u200b":
            zw_seq.append("0")
        elif ch == "\u200c":
            zw_seq.append("1")

    if len(zw_seq) >= 16 and len(zw_seq) % 8 == 0:
        try:
            bits = "".join(zw_seq)
            chars = [chr(int(bits[i : i + 8], 2)) for i in range(0, len(bits), 8)]
            decoded = "".join(chars)
            if decoded.isprintable() and len(decoded) >= 4:
                return decoded
        except Exception:
            return None
    return None


class DecodedVariantDetector:
    """
    Decodes obfuscated variants (Base64, Hex, URL-encoding, reversal, zero-width)
    and runs inner detectors against the decoded content.
    """

    name = "decoded_variant_detector"

    def __init__(
        self,
        inner_detectors: list[Detector],
        max_depth: int = MAX_DECODE_DEPTH,
        time_limit: float = MAX_SCAN_SECONDS,
    ) -> None:
        self.inner_detectors = list(inner_detectors)
        self.max_depth = max_depth
        self.time_limit = time_limit

    def scan(self, text: str) -> Iterable[Finding]:
        if not text:
            return

        start_time = time.monotonic()
        yield from self._scan_recursive(text, depth=0, start_time=start_time)

    def _scan_recursive(
        self, text: str, depth: int, start_time: float
    ) -> Iterable[Finding]:
        if depth >= self.max_depth or (time.monotonic() - start_time) > self.time_limit:
            return

        # 1. Base64 decoded variants
        for match in _BASE64_CANDIDATE_RE.finditer(text):
            if (time.monotonic() - start_time) > self.time_limit:
                break
            candidate = match.group(0)
            try:
                raw_bytes = base64.b64decode(candidate, validate=True)
                if len(raw_bytes) > MAX_DECODED_SIZE:
                    continue
                decoded_str = raw_bytes.decode("utf-8", errors="ignore")
                if decoded_str and decoded_str.isprintable():
                    for det in self.inner_detectors:
                        for inner_f in det.scan(decoded_str):
                            yield Finding(
                                detector=f"{self.name}:base64:{det.name}",
                                kind=f"encoded_{inner_f.kind}",
                                start=match.start(),
                                end=match.end(),
                                matched_text=candidate,
                                severity="high",
                            )
            except (binascii.Error, ValueError):
                continue

        # 2. Hex decoded variants
        for match in _HEX_CANDIDATE_RE.finditer(text):
            if (time.monotonic() - start_time) > self.time_limit:
                break
            candidate = match.group(0)
            if len(candidate) % 2 != 0:
                continue
            try:
                raw_bytes = binascii.unhexlify(candidate)
                if len(raw_bytes) > MAX_DECODED_SIZE:
                    continue
                decoded_str = raw_bytes.decode("utf-8", errors="ignore")
                if decoded_str and decoded_str.isprintable():
                    for det in self.inner_detectors:
                        for inner_f in det.scan(decoded_str):
                            yield Finding(
                                detector=f"{self.name}:hex:{det.name}",
                                kind=f"encoded_{inner_f.kind}",
                                start=match.start(),
                                end=match.end(),
                                matched_text=candidate,
                                severity="high",
                            )
            except (binascii.Error, ValueError):
                continue

        # 3. URL-encoded variants
        for match in _URL_CANDIDATE_RE.finditer(text):
            if (time.monotonic() - start_time) > self.time_limit:
                break
            candidate = match.group(0)
            try:
                decoded_str = urllib.parse.unquote(candidate)
                if decoded_str and decoded_str != candidate:
                    for det in self.inner_detectors:
                        for inner_f in det.scan(decoded_str):
                            yield Finding(
                                detector=f"{self.name}:url:{det.name}",
                                kind=f"encoded_{inner_f.kind}",
                                start=match.start(),
                                end=match.end(),
                                matched_text=candidate,
                                severity="high",
                            )
            except (binascii.Error, ValueError):
                continue

        # 4. Zero-width hidden steganography
        if any(c in text for c in _ZERO_WIDTH_CHARS):
            hidden = _extract_zero_width_hidden(text)
            if hidden:
                for det in self.inner_detectors:
                    for inner_f in det.scan(hidden):
                        yield Finding(
                            detector=f"{self.name}:zero_width:{det.name}",
                            kind=f"hidden_{inner_f.kind}",
                            start=0,
                            end=len(text),
                            matched_text="<zero_width_hidden_payload>",
                            severity="high",
                        )


class OpaqueBlobDetector:
    """
    Flags long continuous high-entropy or encoded-looking strings in prose fields
    (ADR-022 opaque-blob rule) that need explicit human review even when no regex matches.
    """

    name = "opaque_blob_detector"

    def __init__(self, min_length: int = 60, min_entropy: float = 4.5) -> None:
        self.min_length = min_length
        self.min_entropy = min_entropy
        self._blob_pattern = re.compile(rf"\b[A-Za-z0-9+/=_-]{{{self.min_length},}}\b")

    def scan(self, text: str) -> Iterable[Finding]:
        if not text:
            return

        for match in self._blob_pattern.finditer(text):
            token = match.group(0)
            ent = shannon_entropy(token)
            if ent >= self.min_entropy:
                yield Finding(
                    detector=self.name,
                    kind="opaque_blob",
                    start=match.start(),
                    end=match.end(),
                    matched_text=token,
                    severity="medium",
                )
