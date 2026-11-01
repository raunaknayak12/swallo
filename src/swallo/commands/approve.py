"""
Implementation of the 'swallo approve' command.

Per ADR-003, ADR-007, IMPLEMENTATION_PLAN.md Step 4, and Security.md F2/F21:
- Approval state lives in the local cryptographic ledger, keyed by (packet_hash, target).
- Requires interactive confirmation on the controlling terminal (/dev/tty or CONIN$),
  unless explicitly overridden with --force.
- There is NO approve tool in the MCP server; approval MUST be triggered via the CLI.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from swallo.config import get_store_dir
from swallo.errors import UsageError
from swallo.store.db import get_connection, get_or_create_local_key
from swallo.store.ledger import approve
from swallo.terminal import confirm_on_terminal


def run_approve(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="swallo approve",
        description="Grant human approval for a packet to be delivered to a specific IDE target.",
    )
    parser.add_argument("packet_id", help="Packet identifier (pkt_...) or hash to approve.")
    parser.add_argument(
        "--target",
        "-t",
        default="claude_code",
        help="Target IDE or agent adapter (default: claude_code).",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Bypass interactive terminal confirmation.",
    )
    parser.add_argument("--store", type=Path, default=None, help="Store directory override.")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON.")

    args = parser.parse_args(argv)

    store_dir = (args.store or get_store_dir()).resolve()
    db_path = store_dir / "swallo.db"
    key_path = store_dir / "key"

    if not db_path.exists() or not key_path.exists():
        raise UsageError(f"Store at '{store_dir}' not initialized.")

    conn = get_connection(db_path)
    key_bytes = get_or_create_local_key(key_path)

    # 1. Lookup packet hash
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, hash, project FROM packets WHERE id = ? OR hash = ?",
            (args.packet_id, args.packet_id),
        )
        row = cursor.fetchone()
    finally:
        cursor.close()

    if not row:
        raise UsageError(f"Packet '{args.packet_id}' not found in store.")

    pkt_id, pkt_hash, project = row[0], row[1], row[2]

    # 2. Terminal Confirmation check (ADR-007, F21)
    if not args.force:
        prompt = (
            f"Approve packet '{pkt_id}' (project: '{project}') for delivery to '{args.target}'?"
        )
        confirmed = confirm_on_terminal(prompt, default=False)
        if not confirmed:
            msg = f"Approval aborted by user for packet '{pkt_id}'."
            if args.json:
                print(json.dumps({"status": "aborted", "id": pkt_id, "message": msg}))
            else:
                print(msg, file=sys.stderr)
            return 1

    # 3. Write approval to cryptographic ledger
    mac = approve(conn, key_bytes, pkt_hash, args.target)

    result = {
        "status": "approved",
        "id": pkt_id,
        "hash": pkt_hash,
        "target": args.target,
        "mac": mac,
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Packet '{pkt_id}' successfully approved for target '{args.target}'.")
        print(f"  Hash: {pkt_hash}")
        print(f"  MAC:  {mac}")

    return 0

