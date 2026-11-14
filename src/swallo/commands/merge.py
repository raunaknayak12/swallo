"""Implementation of the 'swallo merge' command.

Usage:
    swallo merge <id> [<id> ...] [--into <title>] [--json]

Loads the specified packets from the database, merges them (dedup + conflict
detection), saves the resulting merged packet as a new draft, and prints a
summary of the merge outcome.

Exit codes:
    0  Merge succeeded (conflicts do not cause a non-zero exit -- they need
       resolving but are not errors).
    1  Merge failed (e.g. a packet ID was not found).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from swallo.config import get_store_dir
from swallo.merge.resolve import merge_packets
from swallo.schema.canonical import parse_canonical_json
from swallo.store.db import get_connection
from swallo.store.objects import ObjectStore


def _load_packet(conn: sqlite3.Connection, packet_id: str) -> dict[str, Any] | None:
    """Load a packet dict from the DB by ID prefix or exact match."""
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
        data = parse_canonical_json(raw)
        if not isinstance(data, dict):
            return None
        res: dict[str, Any] = data
        return res
    except Exception:  # noqa: BLE001
        return None


def run_merge(argv: list[str]) -> int:
    """Entry point for 'swallo merge'."""
    parser = argparse.ArgumentParser(
        prog="swallo merge",
        description="Merge two or more packets into a single draft packet.",
    )
    parser.add_argument(
        "ids",
        nargs="+",
        metavar="ID",
        help="Packet IDs to merge (prefix match supported).",
    )
    parser.add_argument(
        "--into",
        metavar="TITLE",
        default=None,
        help="Title for the merged packet.",
    )
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

    packets: list[dict[str, Any]] = []
    with get_connection(db_path) as conn:
        for pid in args.ids:
            packet = _load_packet(conn, pid)
            if packet is None:
                print(f"Error: packet '{pid}' not found.", file=sys.stderr)
                return 1
            packets.append(packet)

    merged = merge_packets(packets, into=args.into)

    canonical_body = json.dumps(merged).encode("utf-8")
    calculated_hash = f"sha256:{hashlib.sha256(canonical_body).hexdigest()}"
    derived_id = f"pkt_{calculated_hash[7:19]}"
    merged["id"] = derived_id

    # Refresh canonical body with assigned ID
    canonical_body = json.dumps(merged).encode("utf-8")
    calculated_hash = f"sha256:{hashlib.sha256(canonical_body).hexdigest()}"

    obj_store = ObjectStore(store_dir)
    obj_store.put(canonical_body)

    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO packets
            (id, hash, schema_version, project, parent, created_at, body, origin, expires_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'), ?, ?, ?)
            """,
            (
                merged["id"],
                calculated_hash,
                str(merged.get("schema_version", "0.1")),
                str(merged.get("project", "default")),
                None,
                canonical_body,
                "cli_merge",
                None,
            ),
        )

    n_conflicts = len(merged.get("conflicts", []))
    n_near_dups = len(merged.get("near_duplicates", []))
    n_items = len(merged.get("items", []))

    result: dict[str, Any] = {
        "merged_id": merged["id"],
        "source_ids": merged.get("merged_from", []),
        "items": n_items,
        "conflicts": n_conflicts,
        "near_duplicates": n_near_dups,
    }

    if args.as_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Merged {len(packets)} packets -> '{merged['id']}'")
        print(f"  Items: {n_items}  |  Conflicts: {n_conflicts}  |  Near-dups: {n_near_dups}")
        if n_conflicts:
            print(
                f"  Warning: {n_conflicts} conflict(s) detected. "
                "Run 'swallo resolve <merged_id> --conflict <cid>' to resolve.",
                file=sys.stderr,
            )

    return 0
