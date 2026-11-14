"""Implementation of the 'swallo resolve' command.

Usage:
    swallo resolve <merged_id> --conflict <cid> (--keep <item_id> | --both)

Loads a merged packet, resolves one conflict (by keeping one item or both),
and saves the updated packet back to the database.

Exit codes:
    0  Conflict resolved successfully.
    1  Error (packet or conflict not found, bad arguments).
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
from swallo.merge.resolve import resolve_conflict
from swallo.schema.canonical import parse_canonical_json
from swallo.store.db import get_connection
from swallo.store.objects import ObjectStore


def _load_packet_json(
    conn: sqlite3.Connection, packet_id: str
) -> tuple[str, dict[str, Any]] | None:
    """Return (raw_json, parsed_dict) for the packet matching *packet_id*."""
    cur = conn.execute(
        "SELECT id, body FROM packets WHERE id = ? OR id LIKE ? OR hash = ? OR hash LIKE ? "
        "ORDER BY created_at DESC LIMIT 1",
        (packet_id, f"{packet_id}%", packet_id, f"{packet_id}%"),
    )
    row = cur.fetchone()
    if row is None:
        return None
    try:
        raw = row[1]
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        parsed_obj = parse_canonical_json(raw)
        if isinstance(parsed_obj, dict):
            return raw, parsed_obj
        return None
    except Exception:  # noqa: BLE001
        return None


def run_resolve(argv: list[str]) -> int:
    """Entry point for 'swallo resolve'."""
    parser = argparse.ArgumentParser(
        prog="swallo resolve",
        description="Resolve a conflict in a merged packet.",
    )
    parser.add_argument("packet_id", metavar="MERGED_ID", help="ID of the merged packet.")
    parser.add_argument("--conflict", required=True, metavar="CID", help="Conflict ID to resolve.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--keep",
        metavar="ITEM_ID",
        default=None,
        help="Keep this item and discard the conflicting item(s).",
    )
    group.add_argument(
        "--both",
        action="store_true",
        default=False,
        help="Keep all conflicting items and drop the conflict marker.",
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

    with get_connection(db_path) as conn:
        result = _load_packet_json(conn, args.packet_id)
        if result is None:
            print(f"Error: packet '{args.packet_id}' not found.", file=sys.stderr)
            return 1

        _raw_json, packet = result

        try:
            updated = resolve_conflict(
                packet,
                args.conflict,
                keep_item_id=args.keep,
                keep_both=args.both,
            )
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        canonical_body = json.dumps(updated).encode("utf-8")
        calculated_hash = f"sha256:{hashlib.sha256(canonical_body).hexdigest()}"
        obj_store = ObjectStore(store_dir)
        obj_store.put(canonical_body)

        conn.execute(
            """
            INSERT OR REPLACE INTO packets
            (id, hash, schema_version, project, parent, created_at, body, origin, expires_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'), ?, ?, ?)
            """,
            (
                updated["id"],
                calculated_hash,
                str(updated.get("schema_version", "0.1")),
                str(updated.get("project", "default")),
                None,
                canonical_body,
                "cli_resolve",
                None,
            ),
        )

    n_remaining = len(updated.get("conflicts", []))
    out: dict[str, Any] = {
        "packet_id": updated["id"],
        "conflict_resolved": args.conflict,
        "conflicts_remaining": n_remaining,
    }

    if args.as_json:
        print(json.dumps(out, indent=2))
    else:
        print(f"Conflict '{args.conflict}' resolved in packet '{updated['id']}'.")
        if n_remaining:
            print(f"  {n_remaining} conflict(s) still remaining.")
        else:
            print("  No conflicts remaining.")

    return 0
