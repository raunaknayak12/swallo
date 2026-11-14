"""End-to-end lifecycle test for the Phase 6 merge system.

Tests the full pipeline:
  merge_packets -> conflict detection -> resolve_conflict -> merged packet structure

This test does NOT require a running database; it tests the merge logic
directly via the Python API.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from swallo.cli import main
from swallo.merge.conflicts import RuleBasedConflictDetector
from swallo.merge.dedupe import deduplicate_items
from swallo.merge.resolve import merge_packets, resolve_conflict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_packet(
    packet_id: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    return {"id": packet_id, "title": f"Packet {packet_id}", "items": items}


def _item(
    value: str,
    item_id: str | None = None,
    topic: str = "",
) -> dict[str, Any]:
    base: dict[str, Any] = {"kind": "constraint", "value": value}
    if item_id:
        base["id"] = item_id
    if topic:
        base["topic"] = topic
    return base


# ---------------------------------------------------------------------------
# merge_packets
# ---------------------------------------------------------------------------


class TestMergePackets:
    def test_empty_input(self) -> None:
        result = merge_packets([])
        assert result["origin"] == "cli_merge"
        assert result["items"] == []
        assert result["conflicts"] == []
        assert result["merged_from"] == []

    def test_single_packet_passthrough(self) -> None:
        p = _make_packet("p1", [_item("use fastapi", "i1"), _item("deploy on railway", "i2")])
        result = merge_packets([p])
        assert result["merged_from"] == ["p1"]
        assert len(result["items"]) == 2

    def test_exact_duplicates_deduped(self) -> None:
        p1 = _make_packet("p1", [_item("use fastapi", "i1")])
        p2 = _make_packet("p2", [_item("use fastapi", "i2")])
        result = merge_packets([p1, p2])
        assert len(result["items"]) == 1

    def test_non_duplicate_items_preserved(self) -> None:
        p1 = _make_packet("p1", [_item("use fastapi")])
        p2 = _make_packet("p2", [_item("use postgresql")])
        result = merge_packets([p1, p2])
        assert len(result["items"]) == 2

    def test_conflicts_detected(self) -> None:
        p1 = _make_packet("p1", [_item("use fastapi", "i1", topic="framework")])
        p2 = _make_packet("p2", [_item("use flask", "i2", topic="framework")])
        result = merge_packets([p1, p2])
        assert len(result["conflicts"]) >= 1
        c = result["conflicts"][0]
        assert c["kind"] == "value_clash"

    def test_merged_from_contains_all_source_ids(self) -> None:
        packets = [_make_packet(f"p{i}", [_item(f"item {i}")]) for i in range(3)]
        result = merge_packets(packets)
        assert set(result["merged_from"]) == {"p0", "p1", "p2"}

    def test_into_title_used(self) -> None:
        p = _make_packet("p1", [])
        result = merge_packets([p], into="My Custom Title")
        assert result["title"] == "My Custom Title"

    def test_result_has_required_keys(self) -> None:
        result = merge_packets([])
        for key in (
            "id", "title", "origin", "merged_from", "items", "conflicts", "near_duplicates"
        ):
            assert key in result, f"Missing key: {key}"

    def test_no_conflict_when_items_agree(self) -> None:
        p1 = _make_packet("p1", [_item("use postgres", "i1", topic="db")])
        p2 = _make_packet("p2", [_item("use postgres", "i2", topic="db")])
        result = merge_packets([p1, p2])
        value_clashes = [c for c in result["conflicts"] if c["kind"] == "value_clash"]
        assert value_clashes == []


# ---------------------------------------------------------------------------
# resolve_conflict
# ---------------------------------------------------------------------------


class TestResolveConflict:
    def _merged_with_conflict(self) -> dict[str, Any]:
        p1 = _make_packet("p1", [_item("use fastapi", "i1", topic="fw")])
        p2 = _make_packet("p2", [_item("use flask", "i2", topic="fw")])
        return merge_packets([p1, p2])

    def test_resolve_keep_one(self) -> None:
        merged = self._merged_with_conflict()
        conflicts = merged["conflicts"]
        assert len(conflicts) >= 1
        conflict_id = conflicts[0]["id"]
        involved = conflicts[0]["item_ids"]

        keep_id = involved[0]
        updated = resolve_conflict(merged, conflict_id, keep_item_id=keep_id)

        assert not any(c["id"] == conflict_id for c in updated["conflicts"])

    def test_resolve_keep_both(self) -> None:
        merged = self._merged_with_conflict()
        conflict_id = merged["conflicts"][0]["id"]
        item_count_before = len(merged["items"])
        updated = resolve_conflict(merged, conflict_id, keep_both=True)

        assert len(updated["items"]) == item_count_before
        assert not any(c["id"] == conflict_id for c in updated["conflicts"])

    def test_resolve_nonexistent_conflict_raises(self) -> None:
        merged = self._merged_with_conflict()
        with pytest.raises(ValueError, match="not found"):
            resolve_conflict(merged, "nonexistent_id", keep_both=True)

    def test_resolve_no_option_raises(self) -> None:
        merged = self._merged_with_conflict()
        conflict_id = merged["conflicts"][0]["id"]
        with pytest.raises(ValueError, match="keep_item_id or keep_both"):
            resolve_conflict(merged, conflict_id)

    def test_resolve_mutually_exclusive_raises(self) -> None:
        merged = self._merged_with_conflict()
        conflict_id = merged["conflicts"][0]["id"]
        with pytest.raises(ValueError, match="mutually exclusive"):
            resolve_conflict(
                merged,
                conflict_id,
                keep_item_id="i1",
                keep_both=True,
            )

    def test_original_packet_not_modified(self) -> None:
        merged = self._merged_with_conflict()
        n_conflicts_before = len(merged["conflicts"])
        conflict_id = merged["conflicts"][0]["id"]
        resolve_conflict(merged, conflict_id, keep_both=True)
        assert len(merged["conflicts"]) == n_conflicts_before


# ---------------------------------------------------------------------------
# Integration: full pipeline
# ---------------------------------------------------------------------------


class TestFullMergeLifecycle:
    def test_merge_then_resolve_then_no_conflicts(self) -> None:
        """Full lifecycle: two conflicting packets merged then conflict resolved."""
        p1 = _make_packet(
            "session_a",
            [
                _item("use fastapi", "ia1", topic="framework"),
                _item("postgres as the primary db", "ia2"),
            ],
        )
        p2 = _make_packet(
            "session_b",
            [
                _item("use flask", "ib1", topic="framework"),
                _item("postgres as the primary db", "ib2"),
            ],
        )

        merged = merge_packets([p1, p2])
        assert len(merged["conflicts"]) >= 1
        values = [i["value"] for i in merged["items"]]
        assert values.count("postgres as the primary db") == 1

        conflict_id = merged["conflicts"][0]["id"]
        resolved = resolve_conflict(merged, conflict_id, keep_both=True)
        assert resolved["conflicts"] == []

    def test_dedup_does_not_remove_different_items(self) -> None:
        items: list[dict[str, Any]] = [
            _item("use fastapi"),
            _item("use postgresql"),
            _item("deploy on railway"),
        ]
        deduped = deduplicate_items(items)
        assert len(deduped) == 3

    def test_conflict_detector_hard_negative(self) -> None:
        """Compatible items (different topics) must NOT produce conflicts."""
        detector = RuleBasedConflictDetector()
        items: list[dict[str, Any]] = [
            _item("postgres", "i1", topic="db"),
            _item("fastapi", "i2", topic="framework"),
            _item("railway", "i3", topic="hosting"),
        ]
        clashes = [c for c in detector.detect(items) if c.kind == "value_clash"]
        assert clashes == []


class TestCliMergeCommands:
    def test_merge_resolve_diff_send_cli(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        store_dir = tmp_path / "store"
        project_root = tmp_path / "repo"
        project_root.mkdir()

        # 1. Init
        assert main(["init", "--store", str(store_dir), "--project", "App", "--json"]) == 0
        capsys.readouterr()

        # 2. Save two packets
        p1 = {
            "schema_version": "0.1",
            "project": "App",
            "created_at": "2026-11-04T00:00:00Z",
            "sources": [
                {
                    "session_id": "s1",
                    "agent": "u",
                    "capture_method": "manual",
                    "captured_at": "2026-11-04T00:00:00Z",
                }
            ],
            "goal": {"text": "Goal A"},
            "items": [
                {
                    "id": "i1",
                    "kind": "decision",
                    "text": "Use Postgres",
                    "topic": "db",
                    "value": "postgres",
                },
                {
                    "id": "i2",
                    "kind": "constraint",
                    "text": "Common constraint",
                    "value": "common",
                },
            ],
        }
        p2 = {
            "schema_version": "0.1",
            "project": "App",
            "created_at": "2026-11-04T00:00:00Z",
            "sources": [
                {
                    "session_id": "s2",
                    "agent": "u",
                    "capture_method": "manual",
                    "captured_at": "2026-11-04T00:00:00Z",
                }
            ],
            "goal": {"text": "Goal B"},
            "items": [
                {
                    "id": "i3",
                    "kind": "decision",
                    "text": "Use MySQL",
                    "topic": "db",
                    "value": "mysql",
                },
                {
                    "id": "i4",
                    "kind": "constraint",
                    "text": "Common constraint",
                    "value": "common",
                },
            ],
        }

        f1 = tmp_path / "p1.json"
        f2 = tmp_path / "p2.json"
        f1.write_text(json.dumps(p1), encoding="utf-8")
        f2.write_text(json.dumps(p2), encoding="utf-8")

        assert main(["save", str(f1), "--store", str(store_dir), "--json"]) == 0
        out1 = json.loads(capsys.readouterr().out)
        id1 = str(out1["id"])

        assert main(["save", str(f2), "--store", str(store_dir), "--json"]) == 0
        out2 = json.loads(capsys.readouterr().out)
        id2 = str(out2["id"])

        # 3. Diff CLI
        assert main(["diff", id1, id2, "--store", str(store_dir), "--json"]) == 0
        diff_out = json.loads(capsys.readouterr().out)
        assert diff_out["summary"]["common"] == 1
        assert diff_out["summary"]["added"] == 1
        assert diff_out["summary"]["removed"] == 1

        # 4. Merge CLI
        assert main(["merge", id1, id2, "--store", str(store_dir), "--json"]) == 0
        merge_out = json.loads(capsys.readouterr().out)
        merged_id = str(merge_out["merged_id"])
        assert merge_out["conflicts"] == 1
        assert merge_out["items"] == 3

        # 5. Resolve CLI
        from swallo.store.db import get_connection

        with get_connection(store_dir / "swallo.db") as conn:
            cur = conn.execute("SELECT body FROM packets WHERE id = ?", (merged_id,))
            p_data = json.loads(cur.fetchone()[0])
            cid = p_data["conflicts"][0]["id"]

        assert (
            main(
                [
                    "resolve",
                    merged_id,
                    "--conflict",
                    cid,
                    "--both",
                    "--store",
                    str(store_dir),
                    "--json",
                ]
            )
            == 0
        )
        resolve_out = json.loads(capsys.readouterr().out)
        assert resolve_out["conflicts_remaining"] == 0

        # 6. Multi-packet send with conflict
        with patch("swallo.commands.approve.confirm_on_terminal", return_value=True):
            assert (
                main(
                    [
                        "approve",
                        id1,
                        "--target",
                        "claude-code",
                        "--store",
                        str(store_dir),
                        "--json",
                    ]
                )
                == 0
            )
            assert (
                main(
                    [
                        "approve",
                        id2,
                        "--target",
                        "claude-code",
                        "--store",
                        str(store_dir),
                        "--json",
                    ]
                )
                == 0
            )

        capsys.readouterr()
        res_fail = main(
            [
                "send",
                id1,
                id2,
                "--store",
                str(store_dir),
                "--project-root",
                str(project_root),
                "--json",
            ]
        )
        assert res_fail == 1

        res_ok = main(
            [
                "send",
                id1,
                id2,
                "--store",
                str(store_dir),
                "--project-root",
                str(project_root),
                "--allow-unresolved",
                "--json",
            ]
        )
        assert res_ok == 0
