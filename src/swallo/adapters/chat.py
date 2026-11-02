"""
Chat target adapter.

Renders context packets for chat interfaces (e.g. ChatGPT, Claude web, Gemini).
Writes the fenced briefing to .swallo/handoff/<packet-id>.md or renders to text
for pasting into conversations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from swallo.adapters.base import (
    BaseAdapter,
    DeliveryResult,
    compute_file_sha256,
)
from swallo.render.briefing import render_briefing
from swallo.render.budget import budget_items, estimate_tokens
from swallo.repo.paths import resolve_in_root


class ChatAdapter(BaseAdapter):
    """Adapter for chat targets delivering fenced briefing documents."""

    name: str = "chat"

    def render(
        self,
        packet_data: dict[str, Any],
        token_budget: int = 4000,
    ) -> str:
        """
        Render a packet into a fenced Markdown briefing string within budget.

        Args:
            packet_data: Canonical packet dictionary.
            token_budget: Maximum tokens allowed.

        Returns:
            Fenced Markdown briefing string.
        """
        items = list(packet_data.get("items", []))
        budget_result = budget_items(items, token_budget)
        budgeted_packet = dict(packet_data)
        budgeted_packet["items"] = budget_result.included_items

        return render_briefing(budgeted_packet)

    def deliver(
        self,
        project_root: Path,
        packet_data: dict[str, Any],
        token_budget: int = 4000,
    ) -> DeliveryResult:
        """
        Deliver a context packet for chat target by writing the handoff file.

        Args:
            project_root: Absolute root path of the project.
            packet_data: Canonical packet dictionary.
            token_budget: Maximum tokens allowed.

        Returns:
            DeliveryResult recording the relative path and hash of the handoff file.
        """
        packet_id = str(packet_data.get("id", "unknown_packet"))
        briefing_content = self.render(packet_data, token_budget=token_budget)
        token_count = estimate_tokens(briefing_content)

        rel_handoff_path = f".swallo/handoff/{packet_id}.md"
        abs_handoff_path = resolve_in_root(project_root, rel_handoff_path)
        abs_handoff_path.parent.mkdir(parents=True, exist_ok=True)
        abs_handoff_path.write_bytes(briefing_content.encode("utf-8"))
        handoff_hash = compute_file_sha256(abs_handoff_path)

        return DeliveryResult(
            target=self.name,
            packet_id=packet_id,
            handoff_path=rel_handoff_path,
            stub_path="",
            handoff_hash=handoff_hash,
            stub_hash="",
            token_count=token_count,
        )
