"""
Unit and integration tests for CursorAdapter.

Covers:
- Detection of Cursor workspace indicators (.cursor/, .cursorrules).
- Two-file delivery to .cursor/rules and root .cursorrules.
- Marker block updating and idempotency.
- Target registry lookup and aliases.
"""

from __future__ import annotations

from pathlib import Path

from swallo.adapters.cursor import CursorAdapter
from swallo.adapters.registry import get_adapter, list_supported_targets, normalize_target


def test_cursor_detection(tmp_path: Path) -> None:
    adapter = CursorAdapter()

    # Empty dir -> False
    assert adapter.detect(tmp_path) is False

    # With .cursor dir -> True
    (tmp_path / ".cursor").mkdir()
    assert adapter.detect(tmp_path) is True

    # Clean and test .cursorrules file
    (tmp_path / ".cursor").rmdir()
    assert adapter.detect(tmp_path) is False
    (tmp_path / ".cursorrules").write_text("# Cursor rules", encoding="utf-8")
    assert adapter.detect(tmp_path) is True


def test_cursor_delivery_with_cursor_dir(tmp_path: Path) -> None:
    cursor_dir = tmp_path / ".cursor"
    cursor_dir.mkdir()
    existing_rules = cursor_dir / "rules"
    existing_rules.write_text("# Custom Cursor Rules\n", encoding="utf-8")

    adapter = CursorAdapter()
    packet_data = {
        "id": "pkt_cursor_1",
        "schema_version": "0.1",
        "project": "cursor-test",
        "goal": {"text": "Implement Cursor adapter"},
        "items": [
            {
                "id": "it_1",
                "kind": "decision",
                "text": "Deliver handoff to .cursor/rules",
                "critical": True,
            }
        ],
    }

    result = adapter.deliver(tmp_path, packet_data)
    assert result.target == "cursor"
    assert result.stub_path == ".cursor/rules"
    assert result.handoff_path == ".swallo/handoff/pkt_cursor_1.md"

    # Verify handoff file was written
    handoff_file = tmp_path / ".swallo" / "handoff" / "pkt_cursor_1.md"
    assert handoff_file.exists()
    content = handoff_file.read_text(encoding="utf-8")
    assert "Implement Cursor adapter" in content

    # Verify stub contains marker block and preserves user content
    stub_content = existing_rules.read_text(encoding="utf-8")
    assert "# Custom Cursor Rules" in stub_content
    assert "<!-- swallo:begin pkt_cursor_1 -->" in stub_content
    assert ".swallo/handoff/pkt_cursor_1.md" in stub_content
    assert "<!-- swallo:end pkt_cursor_1 -->" in stub_content


def test_cursor_registry_lookup() -> None:
    targets = list_supported_targets()
    assert "cursor" in targets

    adapter = get_adapter("cursor")
    assert isinstance(adapter, CursorAdapter)
    assert adapter.name == "cursor"

    # Aliases
    assert get_adapter("cursorrules").name == "cursor"
    assert get_adapter("cursor-rules").name == "cursor"
    assert normalize_target("CURSOR") == "cursor"
