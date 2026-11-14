"""
Implementation of 'swallo status' and 'swallo list' commands.

Per CLI_AND_MCP_SPEC.md section 1:
- Lists packets with their review/approval state (draft, approved, delivered).
- Shows item counts, project, and creation timestamp.
- Never prints sensitive item contents in summary listings.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from swallo.config import get_store_dir
from swallo.errors import UsageError, ValidationError
from swallo.render.sanitize import sanitize_for_display
from swallo.schema.canonical import parse_canonical_json
from swallo.store.db import get_connection


def run_status(argv: list[str]) -> int:
    """Entry point for 'swallo status' and 'swallo list'."""
    parser = argparse.ArgumentParser(
        prog="swallo status",
        description="List stored packets and their current state (draft/approved/delivered).",
    )
    parser.add_argument("--project", default=None, help="Filter by project name.")
    parser.add_argument(
        "--state",
        choices=["all", "draft", "approved", "delivered"],
        default="all",
        help="Filter by approval/delivery state (default: all).",
    )
    parser.add_argument("--store", type=Path, default=None, help="Store directory override.")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON.")

    args = parser.parse_args(argv)

    store_dir = (args.store or get_store_dir()).resolve()
    db_path = store_dir / "swallo.db"

    if not db_path.exists():
        raise UsageError(f"Store at '{store_dir}' not initialized.")

    conn = get_connection(db_path)

    # 1. Fetch packets
    query = "SELECT id, hash, project, created_at, body FROM packets"
    params: list[object] = []
    if args.project:
        query += " WHERE project = ?"
        params.append(args.project)
    query += " ORDER BY created_at DESC"

    cursor = conn.cursor()
    try:
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

        # 2. Fetch approvals
        cursor.execute("SELECT packet_hash, target FROM approvals")
        approval_rows = cursor.fetchall()
        approved_map: dict[str, list[str]] = {}
        for h, target in approval_rows:
            approved_map.setdefault(str(h), []).append(str(target))

        # 3. Fetch delivered events
        cursor.execute(
            "SELECT packet_hash, target FROM events WHERE type = 'delivered' OR type = 'served'"
        )
        delivered_rows = cursor.fetchall()
        delivered_set: set[str] = {str(r[0]) for r in delivered_rows if r[0]}

    finally:
        cursor.close()

    results: list[dict[str, object]] = []
    has_corrupt = False

    for r in rows:
        raw_body = r[4]
        if isinstance(raw_body, (bytes, memoryview)):
            body_raw = bytes(raw_body).decode("utf-8", errors="replace")
        else:
            body_raw = str(raw_body)

        pkt_id, pkt_hash, proj, created_at = (
            str(r[0]),
            str(r[1]),
            str(r[2]),
            str(r[3]),
        )

        # Determine state
        is_approved = pkt_hash in approved_map
        is_delivered = pkt_hash in delivered_set

        if is_delivered:
            state = "delivered"
        elif is_approved:
            state = "approved"
        else:
            state = "draft"

        if args.state != "all" and state != args.state:
            continue

        item_count = 0
        goal_text = ""
        is_corrupt = False
        try:
            body_dict = parse_canonical_json(body_raw)
            if isinstance(body_dict, dict):
                items = body_dict.get("items")
                if isinstance(items, list):
                    item_count = len(items)
                goal_obj = body_dict.get("goal")
                if isinstance(goal_obj, dict):
                    goal_text = str(goal_obj.get("text") or "")
            else:
                is_corrupt = True
        except (ValueError, TypeError, KeyError, ValidationError):
            is_corrupt = True

        if is_corrupt:
            has_corrupt = True
            goal_text = "<corrupt>"

        clean_goal = sanitize_for_display(goal_text)
        clean_proj = sanitize_for_display(proj)
        results.append({
            "id": pkt_id,
            "hash": pkt_hash,
            "project": clean_proj,
            "state": "<corrupt>" if is_corrupt else state,
            "created_at": created_at,
            "items_count": item_count,
            "goal": clean_goal[:40] + ("..." if len(clean_goal) > 40 else ""),
            "approved_targets": approved_map.get(pkt_hash, []),
        })

    if args.json:
        print(json.dumps(results, indent=2))
        return 1 if has_corrupt else 0

    if not results:
        print("No packets found matching criteria.")
        return 0

    print(f"{'PACKET ID':<16} {'STATE':<10} {'ITEMS':<6} {'PROJECT':<14} {'CREATED':<20} {'GOAL'}")
    print("-" * 80)
    for p in results:
        print(
            f"{str(p['id']):<16} "
            f"{str(p['state']):<10} "
            f"{str(p['items_count']):<6} "
            f"{str(p['project']):<14} "
            f"{str(p['created_at'])[:19]:<20} "
            f"{str(p['goal'])}"
        )
    print(f"\nTotal: {len(results)} packet(s).")
    if has_corrupt:
        print(
            "Warning: One or more packet rows were corrupted and could not be fully parsed.",
            file=sys.stderr,
        )
        return 1
    return 0
