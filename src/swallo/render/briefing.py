"""
Markdown handoff document and briefing generator.

Per TRD.md section 7 and IMPLEMENTATION_PLAN.md Step 5:
- Formats context packet data into clean, structured Markdown for agent reference.
- Labels every item with visible provenance (trust tier and capture method).
- Formats goals, decisions, constraints, context, and open questions.
- Wraps entire body in a random CSPRNG fence with inert data notices.
"""

from __future__ import annotations

from typing import Any

from swallo.render.fence import wrap_in_fence
from swallo.render.sanitize import sanitize_for_display


def render_briefing(
    packet_data: dict[str, Any],
    included_items: list[dict[str, Any]] | None = None,
    fenced: bool = True,
) -> str:
    """
    Render a packet into a Markdown handoff document with item provenance.

    Args:
        packet_data: Canonical packet dictionary.
        included_items: Specific subset of items to render (e.g. after budgeting).
                       If None, all items from packet_data['items'] are rendered.
        fenced: Whether to wrap the generated Markdown in a CSPRNG fence.

    Returns:
        Structured Markdown text.
    """
    pkt_id = str(packet_data.get("id", "pkt_unknown"))
    project = str(packet_data.get("project", "default"))
    created_at = str(packet_data.get("created_at", ""))

    lines: list[str] = [
        f"# Context Packet: {pkt_id}",
        "",
        f"- **Project:** `{sanitize_for_display(project)}`",
        f"- **Created:** `{created_at}`",
        f"- **Schema Version:** `{packet_data.get('schema_version', '0.1')}`",
        "",
    ]

    # Goal section
    goal = packet_data.get("goal")
    if isinstance(goal, dict):
        goal_text = str(goal.get("text", "")).strip()
        if goal_text:
            lines.extend([
                "## Goal",
                "",
                sanitize_for_display(goal_text),
                "",
            ])

    # Items section
    items = included_items if included_items is not None else packet_data.get("items", [])
    if isinstance(items, list) and items:
        lines.extend([
            f"## Items ({len(items)})",
            "",
        ])

        for i, item in enumerate(items, 1):
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id", f"it_{i}"))
            kind = str(item.get("kind", "decision")).upper()
            text = sanitize_for_display(str(item.get("text", "")))
            critical = bool(item.get("critical", False))

            # Provenance metadata
            prov = item.get("provenance")
            prov_label = ""
            if isinstance(prov, dict):
                tier = prov.get("trust_tier", "T2")
                method = prov.get("capture_method", "unknown")
                prov_label = f" [{tier} | {method}]"

            crit_badge = " [CRITICAL]" if critical else ""
            lines.append(f"### {i}. [{kind}]{crit_badge}{prov_label} `{item_id}`")
            lines.append("")
            lines.append(text)
            lines.append("")

    raw_markdown = "\n".join(lines)

    if fenced:
        fenced_doc, _ = wrap_in_fence(raw_markdown, title=f"Packet {pkt_id}")
        return fenced_doc

    return raw_markdown
