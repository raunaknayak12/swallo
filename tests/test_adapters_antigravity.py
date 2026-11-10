"""
Unit and integration tests for AntigravityAdapter.

Covers:
- Detection of Antigravity workspace indicators (.agents, AGENTS.md, .gemini).
- Two-file delivery to .agents/AGENTS.md and root AGENTS.md.
- Marker block updating and idempotency.
- Target registry lookup and aliases.
"""

from __future__ import annotations

from pathlib import Path

from swallo.adapters.antigravity import AntigravityAdapter
from swallo.adapters.registry import get_adapter, list_supported_targets, normalize_target


def test_antigravity_detection(tmp_path: Path) -> None:
    adapter = AntigravityAdapter()

    # Empty dir -> False
    assert adapter.detect(tmp_path) is False

    # With .agents dir -> True
    (tmp_path / ".agents").mkdir()
    assert adapter.detect(tmp_path) is True

    # Clean and test AGENTS.md
    (tmp_path / ".agents").rmdir()
    assert adapter.detect(tmp_path) is False
    (tmp_path / "AGENTS.md").write_text("# Agents", encoding="utf-8")
    assert adapter.detect(tmp_path) is True

    # Clean and test .gemini
    (tmp_path / "AGENTS.md").unlink()
    assert adapter.detect(tmp_path) is False
    (tmp_path / ".gemini").mkdir()
    assert adapter.detect(tmp_path) is True


def test_antigravity_delivery_with_agents_dir(tmp_path: Path) -> None:
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    existing_agents_md = agents_dir / "AGENTS.md"
    existing_agents_md.write_text("# User Custom Rules\n", encoding="utf-8")

    adapter = AntigravityAdapter()
    packet_data = {
        "id": "pkt_agy_1",
        "schema_version": "0.1",
        "project": "agy-test",
        "goal": {"text": "Implement adapter support"},
        "items": [
            {
                "id": "it_1",
                "kind": "decision",
                "text": "Use AGENTS.md for instructions",
                "critical": True,
            }
        ],
    }

    result = adapter.deliver(tmp_path, packet_data, token_budget=4000)
    assert result.target == "antigravity"
    assert result.packet_id == "pkt_agy_1"
    assert result.stub_path == ".agents/AGENTS.md"
    assert result.handoff_path == ".swallo/handoff/pkt_agy_1.md"

    # Verify handoff file exists
    handoff_file = tmp_path / ".swallo" / "handoff" / "pkt_agy_1.md"
    assert handoff_file.is_file()
    assert "pkt_agy_1" in handoff_file.read_text(encoding="utf-8")

    # Verify AGENTS.md was updated
    stub_content = existing_agents_md.read_text(encoding="utf-8")
    assert "# User Custom Rules" in stub_content
    assert "<!-- swallo:begin pkt_agy_1 -->" in stub_content
    assert "<!-- swallo:end pkt_agy_1 -->" in stub_content
    assert "# --- SWALLO CONTEXT HANDOFF ---" in stub_content

    # Idempotency: deliver again
    result2 = adapter.deliver(tmp_path, packet_data, token_budget=4000)
    assert result2.stub_hash == result.stub_hash
    stub_content_2 = existing_agents_md.read_text(encoding="utf-8")
    assert stub_content_2.count("<!-- swallo:begin pkt_agy_1 -->") == 1


def test_antigravity_delivery_root_agents_md(tmp_path: Path) -> None:
    adapter = AntigravityAdapter()
    packet_data = {
        "id": "pkt_agy_root",
        "schema_version": "0.1",
        "project": "root-test",
        "goal": {"text": "Deliver to root AGENTS.md"},
        "items": [],
    }

    result = adapter.deliver(tmp_path, packet_data)
    assert result.stub_path == "AGENTS.md"

    root_agents = tmp_path / "AGENTS.md"
    assert root_agents.is_file()
    assert "<!-- swallo:begin pkt_agy_root -->" in root_agents.read_text(encoding="utf-8")


def test_antigravity_registry_and_aliases() -> None:
    targets = list_supported_targets()
    assert "antigravity" in targets
    assert normalize_target("agy") == "antigravity"
    assert normalize_target("gemini") == "antigravity"
    assert normalize_target("ANTIGRAVITY") == "antigravity"

    adapter = get_adapter("antigravity")
    assert isinstance(adapter, AntigravityAdapter)

    adapter_alias = get_adapter("agy")
    assert isinstance(adapter_alias, AntigravityAdapter)
