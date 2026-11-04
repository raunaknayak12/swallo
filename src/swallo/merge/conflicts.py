"""Rule-based conflict detection for packet item merging.

A *conflict* arises when two items share the same ``topic`` field but carry
different normalized values, indicating that they make contradictory claims
about the same subject.

Additionally, items that contain override language -- phrases like
"ignore the earlier", "supersedes", "instead of" -- are flagged, since they
imply that another item in the packet should no longer apply.

Design
------
* ``Conflict`` is a frozen dataclass so it is hashable and safe to store in
  sets / dicts.
* ``ConflictDetector`` is a structural Protocol -- any object with a compatible
  ``detect`` method satisfies it without subclassing.
* ``RuleBasedConflictDetector`` implements the protocol using only the stdlib.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from swallo.merge.normalize import normalize_text, normalized_hash

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

ConflictKind = Literal["value_clash", "override_language"]


@dataclass(frozen=True)
class Conflict:
    """A detected conflict between two or more packet items.

    Attributes:
        id: A unique identifier for this conflict (UUID hex string).
        item_ids: IDs of the items involved in the conflict.
        reason: Human-readable description of why these items conflict.
        kind: Either ``"value_clash"`` (same topic, different values) or
              ``"override_language"`` (item contains superseding language).
    """

    id: str
    item_ids: list[str] = field(compare=False)
    reason: str = field(compare=False)
    kind: ConflictKind = field(compare=False)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict representation."""
        reason_map = {
            "value_clash": "same_topic_different_value",
            "override_language": "override_language",
        }
        return {
            "id": self.id,
            "items": self.item_ids,
            "item_ids": self.item_ids,
            "reason": reason_map.get(self.kind, "same_topic_different_value"),
            "description": self.reason,
            "kind": self.kind,
            "status": "unresolved",
        }


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class ConflictDetector(Protocol):
    """Structural protocol for conflict detectors."""

    def detect(self, items: list[dict[str, Any]]) -> list[Conflict]:
        """Return all conflicts found in *items*."""
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# Heuristic patterns for override language
# ---------------------------------------------------------------------------

_OVERRIDE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bignore\s+the\s+earlier\b", re.IGNORECASE),
    re.compile(r"\binstead\s+of\b", re.IGNORECASE),
    re.compile(r"\bsupersedes?\b", re.IGNORECASE),
    re.compile(r"\breplace\s+with\b", re.IGNORECASE),
    re.compile(r"\bdiscard\b", re.IGNORECASE),
    re.compile(r"\boverrides?\b", re.IGNORECASE),
    re.compile(r"\bno\s+longer\s+applies?\b", re.IGNORECASE),
    re.compile(r"\bcancels?\s+the\s+previous\b", re.IGNORECASE),
]


def _has_override_language(text: str) -> bool:
    """Return True if *text* contains any recognized override phrase."""
    return any(pat.search(text) for pat in _OVERRIDE_PATTERNS)


# ---------------------------------------------------------------------------
# Rule-based implementation
# ---------------------------------------------------------------------------


class RuleBasedConflictDetector:
    """Detect conflicts using topic-based value clash and override heuristics.

    Rule 1 -- Value clash:
        Items that share the same non-empty ``topic`` field but whose
        normalized ``value`` texts hash differently are reported as conflicts.

    Rule 2 -- Override language:
        Items whose ``value`` text contains recognizable superseding language
        (e.g. "supersedes", "ignore the earlier", "discard") are individually
        flagged, because they imply another item in the packet is obsolete.
    """

    def detect(self, items: list[dict[str, Any]]) -> list[Conflict]:
        """Detect and return all conflicts in *items*.

        Args:
            items: A list of packet item dicts.  Each dict is expected to have
                   ``"id"``, ``"topic"`` (optional), and ``"value"`` keys.

        Returns:
            A list of :class:`Conflict` objects (may be empty).
        """
        conflicts: list[Conflict] = []
        conflicts.extend(self._detect_value_clashes(items))
        conflicts.extend(self._detect_override_language(items))
        return conflicts

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _item_id(item: dict[str, Any], index: int) -> str:
        """Return the item's id or fall back to a positional string."""
        return str(item.get("id", f"item_{index}"))

    @staticmethod
    def _detect_value_clashes(
        items: list[dict[str, Any]],
    ) -> list[Conflict]:
        """Group items by topic; flag groups with more than one distinct value."""
        # topic -> list of (item_id, value_hash, value)
        by_topic: dict[str, list[tuple[str, str, str]]] = {}

        for idx, item in enumerate(items):
            topic = str(item.get("topic", "")).strip()
            if not topic:
                continue
            value = str(item.get("value") or item.get("text") or "")
            iid = RuleBasedConflictDetector._item_id(item, idx)
            by_topic.setdefault(topic, []).append((iid, normalized_hash(value), value))

        conflicts: list[Conflict] = []
        for topic, entries in by_topic.items():
            # Collect distinct hashes
            hash_to_entries: dict[str, list[str]] = {}
            for iid, h, _val in entries:
                hash_to_entries.setdefault(h, []).append(iid)

            if len(hash_to_entries) <= 1:
                continue  # all entries agree -- no conflict

            # Flatten all item IDs involved
            all_ids = [iid for iid, _h, _v in entries]
            # Build a readable summary of distinct values
            value_summaries = []
            for h_key, ids in hash_to_entries.items():
                for _eid, eh, ev in entries:
                    if eh == h_key:
                        snippet = normalize_text(ev)[:60]
                        value_summaries.append(f"{ids!r} -> '{snippet}'")
                        break

            reason = (
                f"Topic '{topic}' has {len(hash_to_entries)} conflicting "
                f"values: {'; '.join(value_summaries)}"
            )
            conflicts.append(
                Conflict(
                    id=uuid.uuid4().hex,
                    item_ids=all_ids,
                    reason=reason,
                    kind="value_clash",
                )
            )

        return conflicts

    @staticmethod
    def _detect_override_language(
        items: list[dict[str, Any]],
    ) -> list[Conflict]:
        """Flag items that contain override/superseding language."""
        conflicts: list[Conflict] = []
        for idx, item in enumerate(items):
            value = str(item.get("value") or item.get("text") or "")
            if _has_override_language(value):
                iid = RuleBasedConflictDetector._item_id(item, idx)
                snippet = value[:80].replace("\n", " ")
                conflicts.append(
                    Conflict(
                        id=uuid.uuid4().hex,
                        item_ids=[iid],
                        reason=(
                            f"Item '{iid}' contains override language: '{snippet}...'"
                        ),
                        kind="override_language",
                    )
                )
        return conflicts
