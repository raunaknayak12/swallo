"""
Unit tests for Context Packet Pydantic models, validation limits, and JSON Schema export.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swallo.errors import ValidationError
from swallo.schema.jsonschema import export_json_schema
from swallo.schema.limits import MAX_ITEM_TEXT_LEN, MAX_ITEMS_PER_KIND
from swallo.schema.models import Goal, Item, Packet, Source

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SCHEMAS_DIR = Path(__file__).parents[1] / "docs" / "schemas"


def test_load_v0_1_fixture() -> None:
    fixture_path = FIXTURES_DIR / "v0_1_packet.json"
    data = json.loads(fixture_path.read_text(encoding="utf-8"))

    packet = Packet.model_validate(data)
    assert packet.schema_version == "0.1"
    assert packet.project == "myapp"
    assert packet.goal.text == "Build an open-source context handoff tool"
    assert len(packet.items) == 2
    assert packet.id is not None
    assert packet.id.startswith("pkt_")


def test_ignore_trust_fields_on_load() -> None:
    fixture_path = FIXTURES_DIR / "v0_1_packet.json"
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    data["trust"] = "T0"  # Malicious/fabricated in-file trust claim
    data["sources"][0]["trust"] = "T0"

    packet = Packet.model_validate(data)
    dumped = packet.model_dump()
    assert "trust" not in dumped


def test_item_text_length_limit() -> None:
    item_ok = Item(
        kind="decision",
        text="x" * MAX_ITEM_TEXT_LEN,
    )
    assert len(item_ok.text) == MAX_ITEM_TEXT_LEN

    with pytest.raises(ValidationError, match="Item text exceeds maximum length"):
        Item(
            kind="decision",
            text="x" * (MAX_ITEM_TEXT_LEN + 1),
        )


def test_items_per_kind_limit() -> None:
    items = [
        Item(kind="decision", text=f"Decision number {i}")
        for i in range(MAX_ITEMS_PER_KIND + 1)
    ]
    with pytest.raises(ValidationError, match="Exceeded maximum items for kind 'decision'"):
        Packet(
            created_at="2026-10-31T12:00:00Z",
            project="test",
            sources=[
                Source(
                    session_id="s1",
                    agent="chatgpt",
                    capture_method="paste",
                    captured_at="2026-10-31T12:00:00Z",
                )
            ],
            goal=Goal(text="Test goal"),
            items=items,
        )


def test_control_character_rejection() -> None:
    with pytest.raises(ValidationError, match="control characters"):
        Goal(text="Goal with escape \x1b[31mred\x1b[0m")

    with pytest.raises(ValidationError, match="control characters"):
        Item(kind="constraint", text="Text with null \x00 byte")


def test_repo_state_path_traversal_rejection() -> None:
    fixture_path = FIXTURES_DIR / "v0_1_packet.json"
    data = json.loads(fixture_path.read_text(encoding="utf-8"))

    # Traversal in files dictionary key
    data["repo_state"]["files"] = {"../etc/passwd": "blob:1234"}
    with pytest.raises(ValidationError, match="File paths must be repo-relative"):
        Packet.model_validate(data)

    data["repo_state"]["files"] = {"/absolute/path": "blob:1234"}
    with pytest.raises(ValidationError, match="File paths must be repo-relative"):
        Packet.model_validate(data)


def test_unsupported_schema_version() -> None:
    fixture_path = FIXTURES_DIR / "v0_1_packet.json"
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    data["schema_version"] = "99.0"

    with pytest.raises(ValidationError, match="Unsupported schema_version"):
        Packet.model_validate(data)


def test_json_schema_export_matches_committed_file() -> None:
    committed_schema_path = SCHEMAS_DIR / "v0.1.json"
    assert committed_schema_path.exists(), "Committed JSON schema file must exist"

    committed_data = json.loads(committed_schema_path.read_text(encoding="utf-8"))
    generated_data = export_json_schema()

    assert generated_data == committed_data
