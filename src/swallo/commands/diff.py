"""Implementation of the 'swallo diff' command.

Usage:
    swallo diff <id1> <id2> [--json]

Compares two packets by their item normalized hashes and prints a summary
of items added, removed, and common to both.

Exit codes:
    0  Diff completed (even if packets are identical).
    1  Error (packet not found).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from swallo.config import get_store_dir
from swallo.merge.normalize import normalize_text, normalized_hash
from swallo.store.db import get_connection


def _load_items(conn: Any, packet_id: str) -> list[dict[str, Any]] | None:
    """Return the items list from the packet matching *packet_id*, or None."""
    cur = conn.execute(
        "SELECT body FROM packets WHERE id = ? OR id LIKE ? OR hash = ? OR hash LIKE ? "
        "ORDER BY created_at DESC LIMIT 1",
        (packet_id, f"{packet_id}%", packet_id, f"{packet_id}%"),
    )
    row = cur.fetchone()
    if row is None:
        return None
    try:
        raw = row[0]
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data: dict[str, Any] = json.loads(raw)
        items = data.get("items", [])
        if isinstance(items, list):
            result: list[dict[str, Any]] = items
            return result
        return []
    except Exception:  # noqa: BLE001
        return None


def run_diff(argv: list[str]) -> int:
    """Entry point for 'swallo diff'."""
    parser = argparse.ArgumentParser(
        prog="swallo diff",
        description="Compare two packets and show added / removed / common items.",
    )
    parser.add_argument("id1", metavar="ID1", help="First packet ID.")
    parser.add_argument("id2", metavar="ID2", help="Second packet ID.")
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Machine-readable JSON output.",
    )
    parser.add_argument(
        "--store",
        type=Path,
        default=None,
        help="Store directory override.",
    )

    args = parser.parse_args(argv)

    store_dir = (args.store or get_store_dir()).resolve()
    db_path = store_dir / "swallo.db"
    if not db_path.exists():
        print("Error: swallo store not initialised. Run 'swallo init' first.", file=sys.stderr)
        return 1

    with get_connection(db_path) as conn:
        items1 = _load_items(conn, args.id1)
        if items1 is None:
            print(f"Error: packet '{args.id1}' not found.", file=sys.stderr)
            return 1

        items2 = _load_items(conn, args.id2)
        if items2 is None:
            print(f"Error: packet '{args.id2}' not found.", file=sys.stderr)
            return 1

    # Build hash -> item maps for both packets
    def _build_map(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for item in items:
            value = str(item.get("value") or item.get("text") or "")
            h = normalized_hash(value)
            result[h] = item
        return result

    map1 = _build_map(items1)
    map2 = _build_map(items2)

    hashes1 = set(map1)
    hashes2 = set(map2)

    added_hashes = hashes2 - hashes1
    removed_hashes = hashes1 - hashes2
    common_hashes = hashes1 & hashes2

    def _snippet(item: dict[str, Any]) -> str:
        return normalize_text(str(item.get("value") or item.get("text") or ""))[:70]

    added = [{"hash": h, "snippet": _snippet(map2[h])} for h in sorted(added_hashes)]
    removed = [{"hash": h, "snippet": _snippet(map1[h])} for h in sorted(removed_hashes)]
    common = [{"hash": h, "snippet": _snippet(map1[h])} for h in sorted(common_hashes)]

    out: dict[str, Any] = {
        "id1": args.id1,
        "id2": args.id2,
        "added": added,
        "removed": removed,
        "common": common,
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "common": len(common),
        },
    }

    if args.as_json:
        print(json.dumps(out, indent=2))
    else:
        print(f"diff {args.id1[:8]}..  vs  {args.id2[:8]}..")
        print(
            f"  + {len(added):3d} added"
            f"   - {len(removed):3d} removed"
            f"   = {len(common):3d} common"
        )
        for item in added:
            print(f"  + {item['snippet'][:60]}")
        for item in removed:
            print(f"  - {item['snippet'][:60]}")

    return 0
