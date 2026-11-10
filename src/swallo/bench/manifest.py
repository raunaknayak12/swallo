"""
Benchmark manifest module.

Per BENCHMARKS.md fixture integrity requirements:
- Computes and verifies the SHA-256 hash of the fixture manifest.
- Provides a stable BenchManifest dataclass for use in results.json.
- Manifest hash is deterministic: same seed + count → same hash every time.
"""

from __future__ import annotations

from dataclasses import dataclass

from swallo.bench.fixtures import (
    build_fixture_set,
    fixture_manifest_sha256,
)


@dataclass(frozen=True)
class BenchManifest:
    """Fixture set manifest for integrity verification."""

    seed: int
    count: int
    split: str
    sha256: str


def build_manifest(
    seed: int,
    count: int = 50,
    split: str = "dev",
) -> BenchManifest:
    """
    Build a reproducible fixture manifest.

    Args:
        seed: Random seed for deterministic fixture generation.
        count: Number of fixtures to generate.
        split: Dataset split label ("dev" or "sealed").

    Returns:
        BenchManifest with stable sha256.
    """
    fixtures = build_fixture_set(seed=seed, count=count)
    sha = fixture_manifest_sha256(fixtures)
    return BenchManifest(seed=seed, count=count, split=split, sha256=sha)


def verify_manifest(manifest: BenchManifest) -> bool:
    """
    Re-derive fixtures from manifest parameters and verify the hash matches.

    Args:
        manifest: Stored manifest to verify.

    Returns:
        True if hash matches; False if the manifest has been tampered with.
    """
    fixtures = build_fixture_set(seed=manifest.seed, count=manifest.count)
    expected = fixture_manifest_sha256(fixtures)
    return expected == manifest.sha256

