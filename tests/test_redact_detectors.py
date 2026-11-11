"""
Unit tests for pattern, entropy, and denylist secret detectors.
"""

from __future__ import annotations

from swallo.redact.denylist import DenylistDetector
from swallo.redact.engine import RedactionEngine
from swallo.redact.entropy import EntropyDetector, shannon_entropy
from swallo.redact.patterns import PatternDetector


def test_pattern_detector_aws_and_github() -> None:
    detector = PatternDetector()
    text = (
        "AWS key is AKIA1234567890ABCDEF in environment\n"
        + ("GitHub token: " + "gh" + "p_111122223333444455556666777788889999\n")
    )
    findings = list(detector.scan(text))
    assert len(findings) == 2
    kinds = {f.kind for f in findings}
    assert "aws_access_key" in kinds
    assert "github_token" in kinds


def test_pattern_detector_ai_keys_and_slack() -> None:
    detector = PatternDetector()
    text = (
        "OpenAI: sk-proj-1234567890abcdef1234567890abcdef1234567890abcdef\n"
        "Anthropic: sk-ant-1234567890abcdef1234567890abcdef123456\n"
        + ("Slack: " + "xox" + "b-123456789012-1234567890123-abcdefghijklmnopqrstuvwx\n")
    )
    findings = list(detector.scan(text))
    assert len(findings) == 3
    kinds = {f.kind for f in findings}
    assert "openai_api_key" in kinds
    assert "anthropic_api_key" in kinds
    assert "slack_token" in kinds


def test_pattern_detector_private_key() -> None:
    detector = PatternDetector()
    pem = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA0Y3w...fake_key_material...\n"
        "-----END RSA PRIVATE KEY-----\n"
    )
    findings = list(detector.scan(pem))
    assert len(findings) == 1
    assert findings[0].kind == "private_key"


def test_pattern_detector_bearer_and_password() -> None:
    detector = PatternDetector()
    text = (
        "Authorization: Bearer 1234567890abcdef1234567890abcdef\n"
        "db_connect: password = 'production_super_secret_db_pass'\n"
    )
    findings = list(detector.scan(text))
    assert len(findings) == 2
    kinds = {f.kind for f in findings}
    assert "bearer_token" in kinds
    assert "connection_password" in kinds


def test_entropy_detector_high_and_low() -> None:
    # High entropy token (alphanumeric to ensure clean word-boundary matching)
    high_secret = "k8J2mN9pQ4vX7zL1wE5rT0yU3iO6sA8dF4gH9jK2lZ5x"
    assert shannon_entropy(high_secret) >= 4.3

    low_string = "a" * 32
    assert shannon_entropy(low_string) == 0.0

    detector = EntropyDetector(threshold=4.3, min_length=20)
    text = f"Safe text {low_string} and random token {high_secret} here."
    findings = list(detector.scan(text))

    assert len(findings) == 1
    assert findings[0].matched_text == high_secret
    assert findings[0].kind == "high_entropy_secret"


def test_denylist_detector() -> None:
    detector = DenylistDetector(terms=["ProjectTitan", "internal.corp.local"])
    text = "Deploy projecttitan to internal.corp.local today."
    findings = list(detector.scan(text))

    assert len(findings) == 2
    terms = {f.matched_text.lower() for f in findings}
    assert "projecttitan" in terms
    assert "internal.corp.local" in terms


def test_combined_engine_redaction() -> None:
    engine = RedactionEngine(
        [
            PatternDetector(),
            EntropyDetector(),
            DenylistDetector(["TopSecretProject"]),
        ]
    )

    raw_text = (
        "Project TopSecretProject deployed with AWS key AKIAIOSFODNN7EXAMPLE "
        + ("and token " + "gh" + "p_111122223333444455556666777788889999.")
    )
    result = engine.redact(raw_text, mode="warn")

    assert "AKIAIOSFODNN7EXAMPLE" not in result.text
    assert ("gh" + "p_111122223333444455556666777788889999") not in result.text
    assert "TopSecretProject" not in result.text
    assert result.redacted_count == 3
