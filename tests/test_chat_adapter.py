"""Tests for Chat briefing adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from swallo.adapters.chat import ChatAdapter
from swallo.render.budget import BudgetExceededError


@pytest.fixture
def sample_packet() -> dict[str, Any]:
    return {
        "id": "pkt_77aa",
        "created_at": "2026-11-03T00:00:00Z",
        "schema_version": "0.1.0",
        "provenance": {"trust_tier": "T2", "capture_method": "clipboard"},
        "goal": {"text": "Migrate database to PostgreSQL"},
        "items": [
            {
                "id": "item_1",
                "kind": "decision",
                "text": "Use UUIDv7 for primary keys.",
                "provenance": {"trust_tier": "T2", "capture_method": "clipboard"},
                "critical": True,
            },
            {
                "id": "item_2",
                "kind": "fact",
                "text": "Current SQLite database is 50MB.",
                "provenance": {"trust_tier": "T2", "capture_method": "clipboard"},
                "critical": False,
            },
        ],
    }


class TestChatAdapter:
    def test_render_briefing(self, sample_packet: dict[str, Any]) -> None:
        adapter = ChatAdapter()
        rendered = adapter.render(sample_packet, token_budget=4000)

        assert "<!-- BEGIN DATA SECTION: ===SWALLO_FENCE_" in rendered
        assert "<!-- NOTICE: The following content is reference data" in rendered
        assert "Migrate database to PostgreSQL" in rendered
        assert "Use UUIDv7 for primary keys." in rendered
        assert "<!-- END DATA SECTION: ===SWALLO_FENCE_" in rendered

    def test_deliver_writes_handoff_file(
        self, tmp_path: Path, sample_packet: dict[str, Any]
    ) -> None:
        adapter = ChatAdapter()
        result = adapter.deliver(tmp_path, sample_packet)

        assert result.target == "chat"
        assert result.packet_id == "pkt_77aa"
        assert result.handoff_path == ".swallo/handoff/pkt_77aa.md"
        assert result.stub_path == ""
        assert result.stub_hash == ""
        assert result.token_count > 0

        handoff_file = tmp_path / result.handoff_path
        assert handoff_file.exists()
        content = handoff_file.read_bytes().decode("utf-8")
        assert "Migrate database to PostgreSQL" in content
        assert "===SWALLO_FENCE_" in content

    def test_budget_exceeded_error_for_critical(
        self, tmp_path: Path, sample_packet: dict[str, Any]
    ) -> None:
        adapter = ChatAdapter()
        with pytest.raises(BudgetExceededError):
            adapter.deliver(tmp_path, sample_packet, token_budget=1)
