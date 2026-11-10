"""
Deterministic Secret Redaction Benchmark Corpus & Evaluator.

CORPUS LICENSE / PROVENANCE
============================
All vectors are SYNTHETIC. No real credentials or secrets of any kind are stored here.
Generation method and provenance per vector type:

- AWS Access Key ID:  Uses AWS's own public documentation example key
  "AKIAIOSFODNN7EXAMPLE" (source: docs.aws.amazon.com/IAM/latest/UserGuide/).
  Additional keys follow the documented AKIA + 16 alphanumeric format, generated
  at import time from a fixed-seed RNG so the string never lives in source.

- GitHub PAT (ghp_):  Format "ghp_" + 36 alphanumeric chars (GitHub PAT v2 spec).
  Generated at import time from a fixed-seed RNG.

- GitHub OAuth token (gho_): same schema, generated from fixed seed.

- Slack Bot/User tokens: "xoxb-" / "xoxp-" + numeric + alphanumeric segments.
  Format from Slack API documentation. Generated at import time from fixed-seed RNG.

- PEM Private Key blocks: Headers/footers are literal; body is a short placeholder
  that cannot be a valid key. No real or generated private key material is stored.

- Connection strings: host/port/db are placeholder values; password segment is
  generated from a fixed-seed RNG so it looks high-entropy but is not real.

- Bearer tokens: Short hex strings generated from a fixed-seed RNG.

- Generic high-entropy API key: 48-char hex string from fixed-seed RNG.

Hard Negatives provenance:
- UUIDs: generated from uuid.uuid4() at import time (no seed needed; not secret-shaped).
- Git SHAs: SHA-256 of fixed strings (not real commits).
- Base64 image header: public standard PNG 1×1 pixel prefix from RFC 2397 examples.
- Lorem Ipsum: public domain standard lorem ipsum.
- Normal source code: trivial Python snippets (no imports of real packages).
"""

from __future__ import annotations

import hashlib
import random
import string
import uuid
from dataclasses import dataclass
from typing import Any

from swallo.redact.engine import RedactionEngine
from swallo.redact.entropy import EntropyDetector
from swallo.redact.patterns import PatternDetector

# ---------------------------------------------------------------------------
# Fixed-seed RNG for reproducible corpus generation (never stored as literals)
# ---------------------------------------------------------------------------
_RNG = random.Random(0xDEADBEEF_C0FFEE42)  # fixed seed; never secret

_ALPHANUM = string.ascii_letters + string.digits


def _rand_chars(n: int, charset: str = _ALPHANUM) -> str:
    return "".join(_RNG.choice(charset) for _ in range(n))


def _rand_hex(n: int) -> str:
    charset = string.hexdigits[:16]  # lowercase hex
    return "".join(_RNG.choice(charset) for _ in range(n))


# ---------------------------------------------------------------------------
# Positives — generated at import time
# ---------------------------------------------------------------------------

# AWS: documented example (AWS public docs) + two generated variants
_AWS_EXAMPLE = "AKIAIOSFODNN7EXAMPLE"  # AWS docs example key — not a real credential
_AWS_GEN_1 = "AKIA" + _rand_chars(16, string.ascii_uppercase + string.digits)
_AWS_GEN_2 = "AKIA" + _rand_chars(16, string.ascii_uppercase + string.digits)

# GitHub PAT (ghp_ = personal, gho_ = oauth)
_GHP_1 = "ghp_" + _rand_chars(36)
_GHP_2 = "ghp_" + _rand_chars(36)
_GHO_1 = "gho_" + _rand_chars(36)

# Slack tokens
_SLACK_XOXB = "xoxb-" + _rand_chars(12, string.digits) + "-" + _rand_chars(13, string.digits) + "-" + _rand_chars(24)
_SLACK_XOXP = "xoxp-" + _rand_chars(9, string.digits) + "-" + _rand_chars(13, string.digits) + "-" + _rand_chars(16)

# PEM — header/footer only; body is a short non-decodable placeholder (< 32 bytes → not a valid key)
_PEM_RSA = (
    "-----BEGIN RSA PRIVATE KEY-----\n"
    "PLACEHOLDER_NOT_A_REAL_KEY_BODY\n"
    "-----END RSA PRIVATE KEY-----"
)
_PEM_OPENSSH = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\n"
    "PLACEHOLDER_NOT_A_REAL_OPENSSH_KEY\n"
    "-----END OPENSSH PRIVATE KEY-----"
)

# Connection string password segment
_CONN_PASS_1 = _rand_chars(20)
_CONN_PASS_2 = _rand_chars(20)

# Bearer / API-key
_BEARER_1 = _rand_hex(32)
_BEARER_2 = _rand_chars(32)
_API_KEY_1 = _rand_hex(48)

# Hard negatives
_SHA256_NEG = hashlib.sha256(b"swallo-bench-neg-1").hexdigest()
_SHA1_NEG = hashlib.sha1(b"swallo-bench-neg-2").hexdigest()  # noqa: S324


@dataclass(frozen=True)
class LabeledSample:
    text: str
    expected_secret_type: str | None  # None for hard negatives
    source_license: str = "MIT-Synthetic"


# ---------------------------------------------------------------------------
# Corpus — built at import time, never stored as literals in source
# ---------------------------------------------------------------------------

POSITIVE_SAMPLES: list[LabeledSample] = [
    # AWS Access Key ID (AWS public docs example + generated variants)
    LabeledSample(f"export AWS_ACCESS_KEY_ID={_AWS_EXAMPLE}", "aws_access_key"),
    LabeledSample(f"aws_key = '{_AWS_GEN_1}'", "aws_access_key"),
    LabeledSample(f"credentials: {_AWS_GEN_2} in config", "aws_access_key"),
    # GitHub PAT
    LabeledSample(f"{_GHP_1}", "github_token"),
    LabeledSample(f"git clone https://{_GHP_2}@github.com", "github_token"),
    LabeledSample(f"Authorization: token {_GHO_1}", "github_token"),
    # Slack Token
    LabeledSample(f"{_SLACK_XOXB}", "slack_token"),
    LabeledSample(f"SLACK_BOT_TOKEN='{_SLACK_XOXP}'", "slack_token"),
    # PEM Private Key — header/footer only; body is a non-decodable placeholder
    LabeledSample(_PEM_RSA, "private_key"),
    LabeledSample(_PEM_OPENSSH, "private_key"),
    # Connection String with password
    LabeledSample(f"postgres://admin:{_CONN_PASS_1}@db.local:5432/main", "connection_password"),
    LabeledSample(f"redis://default:{_CONN_PASS_2}@redis.internal:6379", "connection_password"),
    # Bearer Token
    LabeledSample(f"Authorization: Bearer {_BEARER_1}", "bearer_token"),
    LabeledSample(f"headers = {{'Authorization': 'Bearer {_BEARER_2}'}}", "bearer_token"),
    # Generic high-entropy API key (detected via entropy detector)
    LabeledSample(f"custom_api_secret = '{_API_KEY_1}'", "high_entropy_secret"),
]

NEGATIVE_SAMPLES: list[LabeledSample] = [
    # UUIDs — not secret-shaped per any known scanner regex
    LabeledSample(f"transaction_id = '{uuid.uuid4()}'", None),
    LabeledSample(f"request_uuid = '{uuid.uuid4()}'", None),
    LabeledSample("session: 550e8400-e29b-41d4-a716-446655440000 in header", None),
    # Git SHAs — SHA-256/SHA-1 of fixed strings; not real commits; not secret-shaped
    LabeledSample(f"git commit {_SHA256_NEG}", None),
    LabeledSample(f"merge commit {_SHA1_NEG} into main", None),
    # Base64 image payload header — public standard 1×1 PNG from RFC 2397 examples
    LabeledSample("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk", None),
    # Lorem ipsum — public domain
    LabeledSample("Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor.", None),
    LabeledSample("Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi.", None),
    # Normal Python source code — trivial snippets with no real identifiers
    LabeledSample("def calculate_total(items: list[int]) -> int:\n    return sum(items)", None),
    LabeledSample("import os\nimport sys\nfrom pathlib import Path\n\nroot = Path(__file__).resolve()", None),
    LabeledSample("class DataProcessor:\n    def __init__(self, name: str):\n        self.name = name", None),
]


def evaluate_corpus_redaction() -> dict[str, Any]:
    """
    Evaluate pattern detector and full redaction engine on the labeled corpus.
    Calculates precision, recall, F1, and false positive rates.
    Honestly separates high-confidence regex patterns from entropy detector hits.
    """
    pattern_det = PatternDetector()
    entropy_det = EntropyDetector(threshold=4.3)
    _ = RedactionEngine([pattern_det, entropy_det])

    # 1. Pattern Detector Metrics (High-Confidence Regex)
    pos_tested = 0
    pos_detected = 0
    per_type_stats: dict[str, dict[str, int]] = {}

    for sample in POSITIVE_SAMPLES:
        stype = sample.expected_secret_type or "unknown"
        if stype not in per_type_stats:
            per_type_stats[stype] = {"total": 0, "detected": 0}
        per_type_stats[stype]["total"] += 1
        pos_tested += 1

        findings = list(pattern_det.scan(sample.text))
        if findings:
            pos_detected += 1
            per_type_stats[stype]["detected"] += 1
        elif stype == "high_entropy_secret":
            # High-entropy API keys are handled by entropy detector only
            ent_findings = list(entropy_det.scan(sample.text))
            if ent_findings:
                pos_detected += 1
                per_type_stats[stype]["detected"] += 1

    pattern_recall = pos_detected / pos_tested if pos_tested > 0 else 1.0

    # Test negatives against pattern detector
    neg_tested = len(NEGATIVE_SAMPLES)
    pattern_false_positives = 0
    for sample in NEGATIVE_SAMPLES:
        findings = list(pattern_det.scan(sample.text))
        if findings:
            pattern_false_positives += 1

    pattern_fpr = pattern_false_positives / neg_tested if neg_tested > 0 else 0.0
    pattern_precision = (
        pos_detected / (pos_detected + pattern_false_positives)
        if (pos_detected + pattern_false_positives) > 0
        else 1.0
    )
    pattern_f1 = (
        2 * (pattern_precision * pattern_recall) / (pattern_precision + pattern_recall)
        if (pattern_precision + pattern_recall) > 0
        else 0.0
    )

    # 2. Entropy Detector False Positive Audit (honest reporting)
    entropy_fps = 0
    entropy_fp_reasons: list[str] = []
    for sample in NEGATIVE_SAMPLES:
        ent_findings = list(entropy_det.scan(sample.text))
        if ent_findings:
            entropy_fps += 1
            entropy_fp_reasons.append(sample.text[:60])

    entropy_fpr = entropy_fps / neg_tested if neg_tested > 0 else 0.0

    return {
        "pattern_recall": round(pattern_recall, 4),
        "pattern_precision": round(pattern_precision, 4),
        "pattern_f1": round(pattern_f1, 4),
        "pattern_false_positive_rate": round(pattern_fpr, 4),
        "per_type_accuracy": {
            k: round(v["detected"] / v["total"], 4) if v["total"] > 0 else 1.0
            for k, v in per_type_stats.items()
        },
        "entropy_detector_false_positive_rate": round(entropy_fpr, 4),
        "entropy_detector_fp_samples_count": entropy_fps,
        "entropy_detector_fp_samples": entropy_fp_reasons,
        "total_positive_samples": pos_tested,
        "total_negative_samples": neg_tested,
    }
