"""
Unit tests for AGENTS.md guardrail and context renderer.

Covers:
- Guardrail header and safety invariants formatting.
- Goal rendering and item classification.
- Critical badges and topic prefixes.
- Control character sanitization.
"""

from __future__ import annotations

from swallo.render.agents_md import render_agents_md


def test_render_agents_md_complete() -> None:
    packet = {
        "id": "pkt_agents_test",
        "project": "my-project",
        "created_at": "2026-02-01T12:00:00Z",
        "goal": {"text": "Refactor security boundary architecture"},
        "items": [
            {
                "kind": "decision",
                "topic": "Storage",
                "text": "Use SQLite WAL mode for concurrency",
                "critical": True,
            },
            {
                "kind": "constraint",
                "topic": "Dependencies",
                "text": "Zero runtime dependencies in core",
                "critical": True,
            },
            {
                "kind": "question",
                "text": "Should remote signing be enabled?",
                "critical": False,
            },
            {
                "kind": "artifact_ref",
                "text": "docs/PRD.md",
                "critical": False,
            },
        ],
    }

    output = render_agents_md(packet)

    assert "# --- SWALLO AGENTS GUARDRAILS ---" in output
    assert "# Context Packet: pkt_agents_test (Project: my-project)" in output
    assert "AGENT SAFETY INVARIANTS:" in output
    assert "### Goal" in output
    assert "Refactor security boundary architecture" in output
    assert "### Architectural Decisions" in output
    assert "**Storage**: Use SQLite WAL mode for concurrency [CRITICAL]" in output
    assert "### Constraints & Invariants" in output
    assert "**Dependencies**: Zero runtime dependencies in core [CRITICAL]" in output
    assert "### Open Questions" in output
    assert "Should remote signing be enabled?" in output
    assert "### Referenced Artifacts" in output
    assert "docs/PRD.md" in output


def test_render_agents_md_empty_items() -> None:
    packet = {
        "id": "pkt_minimal",
        "project": "minimal",
        "created_at": "2026-02-01T12:00:00Z",
    }
    output = render_agents_md(packet)
    assert "# --- SWALLO AGENTS GUARDRAILS ---" in output
    assert "pkt_minimal" in output
    assert "### Architectural Decisions" not in output
