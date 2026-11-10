"""
Benchmark fixture factories.

Per BENCHMARKS.md Phase 1 requirements:
- Generates deterministic synthetic Packet-like dictionaries for benchmarking.
- Uses a seeded random source for reproducibility across runs and platforms.
- No disk I/O; fixtures are pure in-memory data structures.
- Phase 1 fixtures exercise redaction, latency, and determinism metrics.
"""

from __future__ import annotations

import hashlib
import json
import random
import string
from datetime import UTC, datetime

# ---------------------------------------------------------------------------
# Synthetic secret patterns (safe, non-real values for testing)
# ---------------------------------------------------------------------------

_FAKE_SECRET_TEMPLATES = [
    "sk-proj-{rand}AAAA",
    "ghp_{rand}",
    "AKIA{rand}",
    "xoxb-{rand}-{rand}",
    "glpat-{rand}",
]

_LOREM = (
    "Lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod "
    "tempor incididunt ut labore et dolore magna aliqua ut enim ad minim "
    "veniam quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea "
    "commodo consequat"
).split()


def _lorem_sentence(rng: random.Random, min_w: int = 6, max_w: int = 20) -> str:
    count = rng.randint(min_w, max_w)
    words = [rng.choice(_LOREM) for _ in range(count)]
    return " ".join(words).capitalize() + "."


def _rand_str(rng: random.Random, length: int = 24) -> str:
    return "".join(rng.choices(string.ascii_letters + string.digits, k=length))  # noqa: S311


def _make_fake_secret(rng: random.Random) -> str:
    tmpl = rng.choice(_FAKE_SECRET_TEMPLATES)
    return tmpl.replace("{rand}", _rand_str(rng, 16))


# ---------------------------------------------------------------------------
# Packet fixture builder
# ---------------------------------------------------------------------------

def _make_packet_dict(
    rng: random.Random,
    idx: int,
    inject_secret: bool = False,
) -> dict[str, object]:
    """Build a synthetic packet dict for benchmarking."""
    pkt_id = f"pkt_bench_{idx:04d}"
    project = f"bench-project-{(idx % 5) + 1}"
    items: list[dict[str, object]] = []

    n_items = rng.randint(2, 6)
    kinds = ["decision", "constraint", "question", "artifact_ref"]
    for j in range(n_items):
        text = _lorem_sentence(rng)
        if inject_secret and j == 0:
            # Inject a fake secret into the first item text
            text = text + " Token=" + _make_fake_secret(rng)
        item: dict[str, object] = {
            "id": f"it_{idx:04d}_{j:02d}",
            "kind": rng.choice(kinds),
            "text": text,
            "critical": rng.random() < 0.2,
            "provenance": {
                "trust_tier": rng.choice(["T1", "T2", "T3"]),
                "capture_method": rng.choice(["cli", "mcp", "import"]),
            },
        }
        items.append(item)

    goal_text = _lorem_sentence(rng, min_w=4, max_w=12)

    return {
        "id": pkt_id,
        "schema_version": "0.1",
        "project": project,
        "created_at": datetime(2026, 1, idx % 28 + 1, 12, 0, 0, tzinfo=UTC).isoformat(),
        "goal": {"text": goal_text},
        "items": items,
    }


# ---------------------------------------------------------------------------
# Public fixture set builder
# ---------------------------------------------------------------------------

def build_fixture_set(
    seed: int,
    count: int = 50,
    secret_fraction: float = 0.3,
) -> list[dict[str, object]]:
    """
    Build a reproducible list of synthetic packet dicts.

    Args:
        seed: Random seed for determinism.
        count: Number of packets to generate.
        secret_fraction: Fraction of packets that contain injected fake secrets.

    Returns:
        List of packet-like dictionaries.
    """
    # Intentionally non-cryptographic: deterministic reproducibility is required.
    rng = random.Random(seed)  # noqa: S311
    packets: list[dict[str, object]] = []
    n_with_secret = int(count * secret_fraction)
    for i in range(count):
        inject = i < n_with_secret
        packets.append(_make_packet_dict(rng, i, inject_secret=inject))
    return packets


def canonical_fixture_json(fixtures: list[dict[str, object]]) -> str:
    """
    Serialize fixtures to canonical JSON for manifest hashing.

    Uses sort_keys=True and separators to ensure byte-identical output.
    """
    return json.dumps(fixtures, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def fixture_manifest_sha256(fixtures: list[dict[str, object]]) -> str:
    """Compute SHA-256 hex digest of the canonical fixture JSON."""
    canonical = canonical_fixture_json(fixtures)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
