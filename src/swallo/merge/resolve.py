"""Packet merging and resolution orchestration.

``merge_packets`` is the entry-point for combining multiple context packets
into a single merged packet.  It delegates to the lower-level modules:

* ``normalize`` -- canonical hash computation
* ``dedupe`` -- exact deduplication with provenance merging
* ``conflicts`` -- rule-based conflict detection

The returned merged packet dict is *not* persisted automatically; callers
(typically the ``swallo merge`` CLI command) are responsible for saving it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from swallo.merge.conflicts import Conflict, RuleBasedConflictDetector
from swallo.merge.dedupe import deduplicate_items, find_near_duplicates

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def merge_packets(
    packets: list[dict[str, Any]],
    into: str | None = None,
) -> dict[str, Any]:
    """Merge *packets* into a single combined packet dict.

    The returned dict is a draft packet with:

    * ``id`` -- a fresh UUID hex
    * ``title`` -- ``into`` if supplied, else auto-generated
    * ``origin`` -- ``"cli_merge"``
    * ``merged_from`` -- list of source packet IDs
    * ``items`` -- deduplicated union of all items from all source packets
    * ``near_duplicates`` -- pairs flagged for human review (not auto-merged)
    * ``conflicts`` -- list of :class:`~swallo.merge.conflicts.Conflict`
      dicts detected in the merged item set

    Args:
        packets: A list of packet dicts to merge.  Each dict must have an
                 ``"id"`` key and an ``"items"`` key (list of item dicts).
        into:    Optional title for the merged packet.  Defaults to
                 ``"Merged packet (<n> sources)"``.

    Returns:
        A merged packet dict (not yet persisted).
    """
    if not packets:
        return _empty_merged_packet(into)

    merged_id = uuid.uuid4().hex
    source_ids: list[str] = [str(p.get("id", "")) for p in packets]
    title = into or f"Merged packet ({len(packets)} sources)"
    project = str(packets[0].get("project", "default")) if packets else "default"
    created_at = datetime.now(UTC).isoformat()
    sources: list[dict[str, Any]] = []
    for p in packets:
        s_list = p.get("sources", [])
        if isinstance(s_list, list):
            sources.extend(s_list)
    if not sources:
        sources = [
            {
                "session_id": "merged",
                "agent": "swallo_merge",
                "capture_method": "merged",
                "captured_at": created_at,
            }
        ]

    # 1. Collect all items from all packets
    all_items: list[dict[str, Any]] = []
    for packet in packets:
        items = packet.get("items", [])
        if isinstance(items, list):
            all_items.extend(items)

    # 2. Exact deduplication
    deduped = deduplicate_items(all_items)

    # 3. Near-duplicate detection (for review, not auto-merge)
    near_dup_pairs = find_near_duplicates(deduped, threshold=0.85)
    near_dups = [
        {"index_a": i, "index_b": j, "similarity": round(sim, 4)}
        for i, j, sim in near_dup_pairs
    ]

    # 4. Conflict detection
    detector = RuleBasedConflictDetector()
    raw_conflicts: list[Conflict] = detector.detect(deduped)
    conflict_dicts = [c.as_dict() for c in raw_conflicts]

    return {
        "id": merged_id,
        "title": title,
        "schema_version": "0.1",
        "project": project,
        "created_at": created_at,
        "sources": sources,
        "goal": {"text": title},
        "origin": "cli_merge",
        "merged_from": source_ids,
        "items": deduped,
        "near_duplicates": near_dups,
        "conflicts": conflict_dicts,
    }


def resolve_conflict(
    merged_packet: dict[str, Any],
    conflict_id: str,
    *,
    keep_item_id: str | None = None,
    keep_both: bool = False,
) -> dict[str, Any]:
    """Resolve a conflict in *merged_packet* by keeping one or both items.

    Args:
        merged_packet:  The merged packet dict (as returned by
                        :func:`merge_packets`).
        conflict_id:    The ``id`` of the :class:`~swallo.merge.conflicts.Conflict`
                        to resolve.
        keep_item_id:   ID of the item to keep.  The other conflicting item(s)
                        are removed.  Mutually exclusive with *keep_both*.
        keep_both:      If ``True``, all conflicting items are kept and the
                        conflict record is removed.  Mutually exclusive with
                        *keep_item_id*.

    Returns:
        A new packet dict with the conflict resolved.  The original
        *merged_packet* is not modified.

    Raises:
        ValueError: If *conflict_id* is not found, or if neither
                    *keep_item_id* nor *keep_both* is specified.
    """
    if keep_item_id is None and not keep_both:
        raise ValueError("Specify either keep_item_id or keep_both=True.")
    if keep_item_id is not None and keep_both:
        raise ValueError("keep_item_id and keep_both are mutually exclusive.")

    conflicts: list[dict[str, Any]] = list(merged_packet.get("conflicts", []))
    target = next((c for c in conflicts if c.get("id") == conflict_id), None)
    if target is None:
        raise ValueError(f"Conflict '{conflict_id}' not found in merged packet.")

    involved_ids: list[str] = list(target.get("item_ids", []))
    items: list[dict[str, Any]] = list(merged_packet.get("items", []))

    if keep_both:
        # Just drop the conflict record — keep all items
        updated_items = items
    else:
        # Remove all conflicting items except the one to keep
        def _item_id(item: dict[str, Any], idx: int) -> str:
            return str(item.get("id", f"item_{idx}"))

        discard_ids = {iid for iid in involved_ids if iid != keep_item_id}
        updated_items = [
            item
            for idx, item in enumerate(items)
            if _item_id(item, idx) not in discard_ids
        ]

    # Remove the resolved conflict from the list
    remaining_conflicts = [c for c in conflicts if c.get("id") != conflict_id]

    new_packet = dict(merged_packet)
    new_packet["items"] = updated_items
    new_packet["conflicts"] = remaining_conflicts
    return new_packet


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _empty_merged_packet(into: str | None) -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex,
        "title": into or "Merged packet (0 sources)",
        "origin": "cli_merge",
        "merged_from": [],
        "items": [],
        "near_duplicates": [],
        "conflicts": [],
    }
