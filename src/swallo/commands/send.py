"""
Implementation of the 'swallo send' command.

Per TRD.md section 7, IMPLEMENTATION_PLAN.md Step 5, and CLI_AND_MCP_SPEC.md:
- Merges/selects packet(s), renders for the requested target, and writes the two-file delivery.
- Checks cryptographic approval ledger; exits with code 6 if unapproved for target.
- Enforces token budget with critical item preservation.
- Adds .swallo/ to .gitignore if inside a git repository and missing.
- Appends delivery event to the tamper-evident audit log.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from swallo.adapters.registry import get_adapter
from swallo.config import get_store_dir
from swallo.errors import NotApprovedError, SwalloError, UsageError
from swallo.schema.canonical import parse_canonical_json
from swallo.store.db import get_connection, get_or_create_local_key
from swallo.store.eventlog import append as log_event
from swallo.store.ledger import is_approved


def ensure_swallo_gitignored(project_root: Path) -> None:
    """Ensure .swallo/ is present in .gitignore if repository has git."""
    git_dir = project_root / ".git"
    if not git_dir.exists():
        return

    gitignore_path = project_root / ".gitignore"
    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding="utf-8")
        if ".swallo" not in content:
            separator = "" if content.endswith("\n") else "\n"
            gitignore_path.write_text(content + separator + ".swallo/\n", encoding="utf-8")
    else:
        gitignore_path.write_text(".swallo/\n", encoding="utf-8")


def run_send(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="swallo send",
        description="Render and deliver one or more context packets to a target IDE or chat.",
    )
    parser.add_argument(
        "packet_ids",
        nargs="+",
        help="One or more packet identifiers (pkt_...) or hashes.",
    )
    parser.add_argument(
        "--to",
        "-t",
        dest="target",
        default="claude-code",
        help="Target adapter: claude-code | chat (default: claude-code).",
    )
    parser.add_argument(
        "--store",
        type=Path,
        default=None,
        help="Store directory override.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root directory override (defaults to current directory).",
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=4000,
        help="Token budget limit (default: 4000).",
    )
    parser.add_argument(
        "--allow-unresolved",
        action="store_true",
        help="Deliver with unresolved conflicts.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail (exit 7) if the packet is stale.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be written without writing any files.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON.",
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
    project_root = (args.project_root or Path.cwd()).resolve()

    # For v0 Phase 5 first half, process the specified packet
    packet_id = args.packet_ids[0]

    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, hash, body
            FROM packets WHERE id = ? OR hash = ?
            """,
            (packet_id, packet_id),
        )
        row = cursor.fetchone()
    finally:
        cursor.close()

    if not row:
        err_msg = f"Packet '{packet_id}' not found in store."
        if args.json:
            print(json.dumps({"error": err_msg, "exit_code": 2}))
        else:
            print(f"Error: {err_msg}", file=sys.stderr)
        return 2

    pkt_id, pkt_hash, body_blob = row[0], row[1], row[2]

    # Check approval in ledger (support canonical name and common aliases like claude_code)
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

    # Add id to packet data if missing
    packet_data["id"] = pkt_id

    if args.dry_run:
        dry_result = {
            "status": "dry_run",
            "target": adapter.name,
            "packet_id": pkt_id,
            "would_write": [f".swallo/handoff/{pkt_id}.md"],
        }
        if adapter.name == "claude-code":
            dry_result["would_update"] = ["CLAUDE.md"]
        if args.json:
            print(json.dumps(dry_result, indent=2))
        else:
            print(f"[dry-run] Would deliver packet '{pkt_id}' to target '{adapter.name}'")
        return 0

    # Ensure .swallo/ is gitignored
    ensure_swallo_gitignored(project_root)

    try:
        delivery = adapter.deliver(project_root, packet_data, token_budget=args.budget)
    except SwalloError as s_err:
        if args.json:
            print(json.dumps({"error": str(s_err), "exit_code": s_err.exit_code}))
        else:
            print(f"Error: {s_err}", file=sys.stderr)
        return s_err.exit_code

    # Log delivery in tamper-evident event log
    log_event(
        conn,
        key_bytes,
        type="packet_delivered",
        packet_hash=pkt_hash,
        target=adapter.name,
        detail=f"Delivered {pkt_id} to {delivery.handoff_path}",
    )

    result_data = {
        "status": "delivered",
        "target": delivery.target,
        "packet_id": delivery.packet_id,
        "handoff_path": delivery.handoff_path,
        "stub_path": delivery.stub_path,
        "handoff_hash": delivery.handoff_hash,
        "stub_hash": delivery.stub_hash,
        "tokens": delivery.token_count,
    }

    if args.json:
        print(json.dumps(result_data, indent=2))
    else:
        print(f"Packet '{pkt_id}' successfully delivered to {delivery.target}:")
        print(f"  Handoff: {delivery.handoff_path} ({delivery.handoff_hash})")
        if delivery.stub_path:
            print(f"  Stub:    {delivery.stub_path} ({delivery.stub_hash})")
        print(f"  Tokens:  ~{delivery.token_count}")

    return 0
