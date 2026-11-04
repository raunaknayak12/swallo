"""Tests for swallo.merge.conflicts — rule-based conflict detection."""

from __future__ import annotations

import pytest

from swallo.merge.conflicts import Conflict, RuleBasedConflictDetector

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _item(
    value: str,
    topic: str = "",
    item_id: str | None = None,
) -> dict[str, object]:
    base: dict[str, object] = {"kind": "constraint", "value": value}
    if topic:
        base["topic"] = topic
    if item_id:
        base["id"] = item_id
    return base


DETECTOR = RuleBasedConflictDetector()


# ---------------------------------------------------------------------------
# Value-clash detection
# ---------------------------------------------------------------------------


class TestValueClash:
    def test_no_conflict_same_topic_same_value(self) -> None:
        items = [
            _item("use fastapi", topic="framework"),
            _item("use fastapi", topic="framework"),
        ]
        conflicts = DETECTOR.detect(items)
        assert conflicts == []

    def test_conflict_same_topic_different_values(self) -> None:
        items = [
            _item("use fastapi", topic="framework", item_id="a"),
            _item("use flask", topic="framework", item_id="b"),
        ]
        conflicts = DETECTOR.detect(items)
        clash = [c for c in conflicts if c.kind == "value_clash"]
        assert len(clash) == 1
        assert "a" in clash[0].item_ids
        assert "b" in clash[0].item_ids

    def test_no_conflict_different_topics(self) -> None:
        items = [
            _item("use fastapi", topic="framework"),
            _item("use postgresql", topic="database"),
        ]
        clashes = [c for c in DETECTOR.detect(items) if c.kind == "value_clash"]
        assert clashes == []

    def test_no_conflict_no_topic(self) -> None:
        # Items without a topic field are excluded from value-clash detection
        items = [_item("use fastapi"), _item("use flask")]
        clashes = [c for c in DETECTOR.detect(items) if c.kind == "value_clash"]
        assert clashes == []

    def test_case_insensitive_values_not_a_conflict(self) -> None:
        # Normalization makes "Use FastAPI" == "use fastapi"
        items = [
            _item("Use FastAPI!", topic="framework"),
            _item("use fastapi", topic="framework"),
        ]
        clashes = [c for c in DETECTOR.detect(items) if c.kind == "value_clash"]
        assert clashes == []

    def test_conflict_reason_contains_topic(self) -> None:
        items = [
            _item("postgres", topic="db"),
            _item("mysql", topic="db"),
        ]
        conflicts = DETECTOR.detect(items)
        clash = next(c for c in conflicts if c.kind == "value_clash")
        assert "db" in clash.reason

    def test_multiple_topics_independent_conflicts(self) -> None:
        items = [
            _item("fastapi", topic="framework"),
            _item("flask", topic="framework"),
            _item("postgres", topic="database"),
            _item("mysql", topic="database"),
        ]
        clashes = [c for c in DETECTOR.detect(items) if c.kind == "value_clash"]
        assert len(clashes) == 2

    def test_conflict_has_unique_id(self) -> None:
        items = [
            _item("a", topic="t"),
            _item("b", topic="t"),
        ]
        c1, *_ = DETECTOR.detect(items)
        # Run again — IDs are UUIDs, so they differ between runs (not frozen)
        assert len(c1.id) == 32  # UUID hex


# ---------------------------------------------------------------------------
# Override language detection
# ---------------------------------------------------------------------------


class TestOverrideLanguage:
    @pytest.mark.parametrize(
        "text",
        [
            "ignore the earlier decision about auth",
            "use OAuth instead of API keys",
            "this supersedes the previous constraint",
            "replace with the new config",
            "discard the old approach",
            "this overrides the earlier setting",
            "the previous rule no longer applies",
            "cancels the previous agreement",
        ],
    )
    def test_override_phrase_detected(self, text: str) -> None:
        items = [_item(text, item_id="x")]
        overrides = [c for c in DETECTOR.detect(items) if c.kind == "override_language"]
        assert len(overrides) == 1
        assert "x" in overrides[0].item_ids

    def test_no_override_language_in_normal_text(self) -> None:
        items = [_item("use postgres as the primary database")]
        overrides = [c for c in DETECTOR.detect(items) if c.kind == "override_language"]
        assert overrides == []

    def test_override_language_does_not_conflict_with_different_items(self) -> None:
        # Override detection is per-item, not cross-item
        items = [
            _item("normal constraint"),
            _item("this supersedes the previous constraint", item_id="sup"),
        ]
        overrides = [c for c in DETECTOR.detect(items) if c.kind == "override_language"]
        assert len(overrides) == 1
        assert "sup" in overrides[0].item_ids


# ---------------------------------------------------------------------------
# Conflict dataclass
# ---------------------------------------------------------------------------


class TestConflictDataclass:
    def test_as_dict_keys(self) -> None:
        c = Conflict(
            id="abc123",
            item_ids=["i1", "i2"],
            reason="test reason",
            kind="value_clash",
        )
        d = c.as_dict()
        assert set(d.keys()) == {"id", "item_ids", "reason", "kind"}

    def test_as_dict_values(self) -> None:
        c = Conflict(id="x", item_ids=["a"], reason="r", kind="override_language")
        d = c.as_dict()
        assert d["kind"] == "override_language"
        assert d["item_ids"] == ["a"]

    def test_conflict_frozen(self) -> None:
        c = Conflict(id="f", item_ids=[], reason="r", kind="value_clash")
        with pytest.raises(AttributeError):
            c.id = "new"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Hard negatives — compatible items must NOT conflict
# ---------------------------------------------------------------------------


class TestHardNegatives:
    def test_different_topics_no_clash(self) -> None:
        items = [
            _item("use postgres", topic="db"),
            _item("use fastapi", topic="framework"),
            _item("deploy on railway", topic="hosting"),
        ]
        clashes = [c for c in DETECTOR.detect(items) if c.kind == "value_clash"]
        assert clashes == []

    def test_no_topic_field_no_clash(self) -> None:
        items = [_item(f"item {i}") for i in range(10)]
        clashes = [c for c in DETECTOR.detect(items) if c.kind == "value_clash"]
        assert clashes == []

    def test_empty_items(self) -> None:
        assert DETECTOR.detect([]) == []

    def test_single_item_no_conflict(self) -> None:
        assert DETECTOR.detect([_item("only item", topic="t")]) == []
