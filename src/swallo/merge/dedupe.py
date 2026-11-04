"""Exact and near-duplicate deduplication for packet items.

Design
------
*Exact deduplication* uses SHA-256 hashes of the normalized item text
(see ``normalize.normalized_hash``).  When two items hash to the same value
they are considered identical content; their provenance records are merged
(taking the highest trust tier and union-ing capture methods).

*Near-duplicate detection* uses token-set Jaccard similarity computed
entirely with the Python standard library.  Items whose normalized texts
share >= ``threshold`` of their word-token Jaccard similarity are flagged
as near-duplicates for human review — they are **not** auto-merged.

Trust tier ordering (lowest → highest confidence):
  T0 (highest) → T1 → T2 → T3 (lowest)
When merging provenance the tier with the *lower number* wins (T0 > T1).
"""

from __future__ import annotations

from typing import Any

from swallo.merge.normalize import normalize_text, normalized_hash

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

Item = dict[str, Any]
Provenance = dict[str, Any]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TRUST_ORDER: dict[str, int] = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}


def _tier_rank(tier: str) -> int:
    """Return a sortable rank for a trust tier string.

    Lower rank == higher trust (T0 is most trusted).
    Unknown tiers are placed at the bottom (rank 99).
    """
    return _TRUST_ORDER.get(tier, 99)


def _merge_provenance(a: Provenance, b: Provenance) -> Provenance:
    """Merge two provenance dicts, keeping the higher-trust tier.

    Capture methods are union-ed; all other fields come from the
    higher-trust record.
    """
    rank_a = _tier_rank(str(a.get("trust_tier", "T3")))
    rank_b = _tier_rank(str(b.get("trust_tier", "T3")))
    # Pick the base from the higher-trust record (lower rank number)
    base, other = (a, b) if rank_a <= rank_b else (b, a)
    merged = dict(base)
    # Union capture methods
    methods_base: set[str] = set(base.get("capture_methods", []))
    methods_other: set[str] = set(other.get("capture_methods", []))
    if methods_base or methods_other:
        merged["capture_methods"] = sorted(methods_base | methods_other)
    return merged


def jaccard_similarity(text_a: str, text_b: str) -> float:
    """Return the token-set Jaccard similarity between two strings.

    Tokens are produced by splitting the *normalized* form of each string
    on whitespace.  Punctuation has already been stripped by normalization.

    Returns a float in [0.0, 1.0].  Returns 1.0 if both strings are empty.
    """
    tokens_a = set(normalize_text(text_a).split())
    tokens_b = set(normalize_text(text_b).split())
    if not tokens_a and not tokens_b:
        return 1.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def deduplicate_items(items: list[Item]) -> list[Item]:
    """Remove exact duplicates from *items*, merging their provenance.

    Items are compared by the SHA-256 hash of their normalized ``value``
    field.  The first occurrence is kept; subsequent duplicates have their
    ``provenance`` merged into it.

    Args:
        items: A list of packet item dicts.  Each dict is expected to have
               a ``"value"`` key (string) and optionally a ``"provenance"``
               key (dict).

    Returns:
        A deduplicated list of items preserving the original order of first
        occurrence.
    """
    seen: dict[str, int] = {}  # hash → index in result
    result: list[Item] = []

    for item in items:
        value = str(item.get("value") or item.get("text") or "")
        h = normalized_hash(value)

        if h in seen:
            # Merge provenance into the existing item
            existing = result[seen[h]]
            prov_existing: Provenance = dict(existing.get("provenance", {}))
            prov_new: Provenance = dict(item.get("provenance", {}))
            if prov_existing or prov_new:
                existing["provenance"] = _merge_provenance(prov_existing, prov_new)
        else:
            seen[h] = len(result)
            result.append(dict(item))

    return result


def find_near_duplicates(
    items: list[Item],
    threshold: float = 0.85,
) -> list[tuple[int, int, float]]:
    """Find pairs of near-duplicate items by Jaccard similarity.

    Pairs whose normalized token-set Jaccard similarity is >= *threshold*
    (but are **not** exact duplicates) are returned for human review.
    Exact duplicates (similarity == 1.0 AND same hash) are excluded because
    ``deduplicate_items`` handles those.

    Args:
        items: A list of packet item dicts.
        threshold: Minimum Jaccard similarity to report (0.0–1.0).

    Returns:
        A list of ``(index_i, index_j, similarity)`` triples, sorted by
        similarity descending.
    """
    pairs: list[tuple[int, int, float]] = []
    n = len(items)

    for i in range(n):
        value_i = str(items[i].get("value") or items[i].get("text") or "")
        hash_i = normalized_hash(value_i)

        for j in range(i + 1, n):
            value_j = str(items[j].get("value") or items[j].get("text") or "")
            hash_j = normalized_hash(value_j)

            # Skip exact duplicates — handled by deduplicate_items
            if hash_i == hash_j:
                continue

            sim = jaccard_similarity(value_i, value_j)
            if sim >= threshold:
                pairs.append((i, j, sim))

    pairs.sort(key=lambda t: t[2], reverse=True)
    return pairs
