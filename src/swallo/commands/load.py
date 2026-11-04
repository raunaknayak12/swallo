"""
Implementation of the 'swallo load' command.

Per CLI_AND_MCP_SPEC.md and COMMANDS.md:
- Renders an approved packet's briefing to stdout (for copying/pasting into chats).
- Checks cryptographic approval ledger; exits with code 6 if unapproved for target.
- Enforces token budget with critical item preservation.
- When --copied flag is given (or confirmed), records a 'copied' event in the event log.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from swallo.adapters.chat import ChatAdapter
from swallo.adapters.registry import get_adapter
from swallo.config import get_store_dir
from swallo.errors import NotApprovedError, SwalloError, UsageError
from swallo.schema.canonical import parse_canonical_json
from swallo.store.db import get_connection, get_or_create_local_key
from swallo.store.eventlog import append as log_event
from swallo.store.ledger import is_approved


def run_load(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="swallo load",
        description="Render an approved context packet to stdout for pasting into a chat.",
    )
    parser.add_argument("packet_id", help="Packet identifier (pkt_...) or hash.")
    parser.add_argument(
        "--to",
        "-t",
        dest="target",
        default="chat",
        help="Target chat or environment: chat | claude-code (default: chat).",
    )
    parser.add_argument(
        "--copied",
        action="store_true",
        help="Record a 'copied' event in the handoff ledger.",
    )
    parser.add_argument(
        "--store",
        type=Path,
        default=None,
        help="Store directory override.",
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=4000,
        help="Token budget limit (default: 4000).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON metadata alongside or instead of raw text.",
    )

    args = parser.parse_args(argv)

    try:
        adapter = get_adapter(args.target)
    except UsageError as err:
        if args.json:
            print(json.dumps({"error": str(err), "exit_code": err.exit_code}))
        else:
            print(f"Error: {err}", file=sys.stderr)
        return err.exit_code

    store_dir = (args.store or get_store_dir()).resolve()
    db_path = store_dir / "swallo.db"
    key_path = store_dir / "key"

    if not db_path.exists() or not key_path.exists():
        err_msg = f"Store at '{store_dir}' not initialized."
        if args.json:
            print(json.dumps({"error": err_msg, "exit_code": 2}))
        else:
            print(f"Error: {err_msg}", file=sys.stderr)
        return 2

    conn = get_connection(db_path)
    key_bytes = get_or_create_local_key(key_path)

    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, hash, body
            FROM packets WHERE id = ? OR hash = ?
            """,
            (args.packet_id, args.packet_id),
        )
        row = cursor.fetchone()
    finally:
        cursor.close()

    if not row:
        err_msg = f"Packet '{args.packet_id}' not found in store."
        if args.json:
            print(json.dumps({"error": err_msg, "exit_code": 2}))
        else:
            print(f"Error: {err_msg}", file=sys.stderr)
        return 2

    pkt_id, pkt_hash, body_blob = row[0], row[1], row[2]

    # Check approval in ledger
    approved = is_approved(conn, key_bytes, pkt_hash, adapter.name)
    if not approved and adapter.name == "claude-code":
        approved = is_approved(conn, key_bytes, pkt_hash, "claude_code")

    if not approved:
        not_approved_err = NotApprovedError(
            f"Packet '{pkt_id}' is not approved for target '{adapter.name}'. "
            f"Run 'swallo approve {pkt_id} --target {adapter.name}' first."
        )
        if args.json:
            print(
                json.dumps(
                    {"error": str(not_approved_err), "exit_code": not_approved_err.exit_code}
                )
            )
        else:
            print(f"Error: {not_approved_err}", file=sys.stderr)
        return int(not_approved_err.exit_code)

    try:
        raw_parsed = parse_canonical_json(body_blob)
        if not isinstance(raw_parsed, dict):
            raise ValueError("Expected dictionary object for packet body")
        packet_data: dict[str, Any] = dict(raw_parsed)
    except Exception as exc:
        err_msg = f"Corrupted packet body: {exc}"
        if args.json:
            print(json.dumps({"error": err_msg, "exit_code": 3}))
        else:
            print(f"Error: {err_msg}", file=sys.stderr)
        return 3

    packet_data["id"] = pkt_id

    # Render briefing using ChatAdapter or general briefing renderer
    chat_adapter = adapter if isinstance(adapter, ChatAdapter) else ChatAdapter()
    try:
        rendered_text = chat_adapter.render(packet_data, token_budget=args.budget)
    except SwalloError as s_err:
        if args.json:
            print(json.dumps({"error": str(s_err), "exit_code": s_err.exit_code}))
        else:
            print(f"Error: {s_err}", file=sys.stderr)
        return s_err.exit_code

    # If --copied flag is present, record 'copied' event
    if args.copied:
        log_event(
            conn,
            key_bytes,
            type="copied",
            packet_hash=pkt_hash,
            target=adapter.name,
            detail=f"Packet {pkt_id} copied to clipboard for {adapter.name}",
        )

    if args.json:
        result_data = {
            "status": "loaded",
            "packet_id": pkt_id,
            "target": adapter.name,
            "copied": args.copied,
            "content": rendered_text,
        }
        print(json.dumps(result_data, indent=2))
    else:
        print(rendered_text)

    return 0
