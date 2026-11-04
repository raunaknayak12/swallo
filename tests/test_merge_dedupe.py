"""Tests for swallo.merge.dedupe — deduplication and near-duplicate detection."""

from __future__ import annotations

from swallo.merge.dedupe import (
    deduplicate_items,
    find_near_duplicates,
    jaccard_similarity,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _item(
    value: str,
    trust_tier: str = "T2",
    capture_methods: list[str] | None = None,
) -> dict[str, object]:
    return {
        "kind": "constraint",
        "value": value,
        "provenance": {
            "trust_tier": trust_tier,
            "capture_methods": capture_methods or ["chat"],
        },
    }


# ---------------------------------------------------------------------------
# jaccard_similarity
# ---------------------------------------------------------------------------

class TestJaccardSimilarity:
    def test_identical_strings(self) -> None:
        assert jaccard_similarity("hello world", "hello world") == 1.0

    def test_completely_different(self) -> None:
        assert jaccard_similarity("foo bar", "baz qux") == 0.0

    def test_partial_overlap(self) -> None:
        sim = jaccard_similarity("the cat sat on the mat", "the cat sat on the hat")
        # 5 tokens shared (the, cat, sat, on, the→set, mat/hat differ)
        # tokens_a = {the, cat, sat, on, mat}, tokens_b = {the, cat, sat, on, hat}
        # intersection=4, union=6 → 4/6 ≈ 0.667
        assert 0.5 < sim < 1.0

    def test_both_empty(self) -> None:
        assert jaccard_similarity("", "") == 1.0

    def test_one_empty(self) -> None:
        assert jaccard_similarity("hello", "") == 0.0

    def test_case_insensitive(self) -> None:
        # Normalization lowercases — should be identical
        assert jaccard_similarity("Hello World", "hello world") == 1.0

    def test_punctuation_stripped(self) -> None:
        # Punctuation is stripped during normalization
        assert jaccard_similarity("hello, world!", "hello world") == 1.0


# ---------------------------------------------------------------------------
# deduplicate_items
# ---------------------------------------------------------------------------

class TestDeduplicateItems:
    def test_no_duplicates(self) -> None:
        items = [_item("foo"), _item("bar")]
        result = deduplicate_items(items)
        assert len(result) == 2

    def test_exact_duplicate_removed(self) -> None:
        items = [_item("hello world"), _item("hello world")]
        result = deduplicate_items(items)
        assert len(result) == 1
        assert result[0]["value"] == "hello world"

    def test_case_insensitive_dedup(self) -> None:
        items = [_item("Hello World"), _item("hello world")]
        result = deduplicate_items(items)
        assert len(result) == 1

    def test_punctuation_insensitive_dedup(self) -> None:
        items = [_item("Hello, World!"), _item("hello world")]
        result = deduplicate_items(items)
        assert len(result) == 1

    def test_provenance_merged_keeps_higher_trust(self) -> None:
        items = [
            _item("use fastapi", trust_tier="T1"),
            _item("use fastapi", trust_tier="T0"),
        ]
        result = deduplicate_items(items)
        assert len(result) == 1
        prov = result[0]["provenance"]
        assert prov["trust_tier"] == "T0"

    def test_provenance_capture_methods_unioned(self) -> None:
        items = [
            _item("deploy on railway", capture_methods=["chat"]),
            _item("deploy on railway", capture_methods=["document"]),
        ]
        result = deduplicate_items(items)
        assert len(result) == 1
        methods = result[0]["provenance"]["capture_methods"]
        assert set(methods) == {"chat", "document"}

    def test_order_of_first_occurrence_preserved(self) -> None:
        items = [_item("first"), _item("second"), _item("first")]
        result = deduplicate_items(items)
        assert [r["value"] for r in result] == ["first", "second"]

    def test_empty_list(self) -> None:
        assert deduplicate_items([]) == []

    def test_single_item(self) -> None:
        items = [_item("only one")]
        assert len(deduplicate_items(items)) == 1

    def test_three_duplicates(self) -> None:
        items = [_item("dup"), _item("dup"), _item("dup")]
        assert len(deduplicate_items(items)) == 1


# ---------------------------------------------------------------------------
# find_near_duplicates
# ---------------------------------------------------------------------------

class TestFindNearDuplicates:
    def test_no_near_duplicates_below_threshold(self) -> None:
        items = [_item("the cat sat on the mat"), _item("dogs enjoy playing fetch")]
        pairs = find_near_duplicates(items, threshold=0.85)
        assert pairs == []

    def test_detects_near_duplicate(self) -> None:
        # Very similar sentences — only one word different
        items = [
            _item("use postgres as the primary database"),
            _item("use postgresql as the primary database"),
        ]
        pairs = find_near_duplicates(items, threshold=0.5)
        assert len(pairs) >= 1
        i, j, sim = pairs[0]
        assert i == 0 and j == 1
        assert sim > 0.5

    def test_exact_duplicates_excluded(self) -> None:
        # Exact duplicates (same hash) should NOT appear in near-dup pairs
        items = [_item("hello world"), _item("hello world")]
        pairs = find_near_duplicates(items, threshold=0.0)
        assert pairs == []

    def test_sorted_by_similarity_descending(self) -> None:
        items = [
            _item("the cat sat on the mat"),
            _item("the cat sat on the hat"),
            _item("completely unrelated text string"),
            _item("the cat sat on the bat"),
        ]
        pairs = find_near_duplicates(items, threshold=0.0)
        sims = [p[2] for p in pairs]
        assert sims == sorted(sims, reverse=True)

    def test_empty_list(self) -> None:
        assert find_near_duplicates([]) == []

    def test_single_item(self) -> None:
        assert find_near_duplicates([_item("alone")]) == []

    def test_threshold_boundary(self) -> None:
        items = [
            _item("use fastapi for the backend api"),
            _item("use flask for the backend api"),
        ]
        # With a very high threshold no pairs should be reported
        pairs_high = find_near_duplicates(items, threshold=0.99)
        assert pairs_high == []
        # With a low threshold at least one pair should appear
        pairs_low = find_near_duplicates(items, threshold=0.3)
        assert len(pairs_low) >= 1
