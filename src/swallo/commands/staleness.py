"""
Implementation of the 'swallo staleness' command.

Per TRD.md section 9.1, CLI_AND_MCP_SPEC.md section 1, and Security.md F18:
- Compares a packet's recorded repo_state against the current repository HEAD.
- Detects modified, deleted, or renamed referenced files, and diverged commits.
- Reports whether drift is critical and whether an unexpired acknowledgment exists.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from swallo.config import get_store_dir
from swallo.errors import UsageError
from swallo.repo.gitstate import get_repo_root
from swallo.repo.staleness import check_staleness
from swallo.schema.canonical import parse_canonical_json
from swallo.schema.models import Packet
from swallo.store.db import get_connection, get_or_create_local_key


def _lookup_packet(conn: sqlite3.Connection, identifier: str) -> tuple[str, str, str] | None:
    """
    Look up packet by ID, prefix, or hash.
    Returns (id, hash, body_json) or None.
    """
    cur = conn.execute(
        """
        SELECT id, hash, body FROM packets
        WHERE id = ? OR id LIKE ? OR hash = ? OR hash LIKE ?
        ORDER BY created_at DESC LIMIT 1
        """,
        (identifier, f"{identifier}%", identifier, f"{identifier}%"),
    )
    row = cur.fetchone()
    if row is None:
        return None
    raw_body = row[2]
    if isinstance(raw_body, (bytes, memoryview)):
        body_str = bytes(raw_body).decode("utf-8", errors="replace")
    else:
        body_str = str(raw_body)
    return str(row[0]), str(row[1]), body_str


def run_staleness(argv: list[str]) -> int:
    """Entry point for 'swallo staleness' command."""
    parser = argparse.ArgumentParser(
        prog="swallo staleness",
        description="Check whether the repository drifted since a packet was created.",
    )
    parser.add_argument("id", metavar="ID", help="Packet ID or hash to check.")
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="Repository root path (defaults to auto-detection from current directory).",
    )
    parser.add_argument("--project", default=None, help="Project name filter.")
    parser.add_argument("--store", type=Path, default=None, help="Store directory override.")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON.")

    args = parser.parse_args(argv)

    store_dir = (args.store or get_store_dir()).resolve()
    db_path = store_dir / "swallo.db"
    key_path = store_dir / "key"

    if not db_path.exists():
        raise UsageError(f"Store at '{store_dir}' not initialized.")

    conn = get_connection(db_path)
    key_bytes = get_or_create_local_key(key_path) if key_path.exists() else None

    # Resolve repository root
    if args.repo:
        repo_root = args.repo.resolve()
    else:
        detected = get_repo_root(Path.cwd())
        repo_root = detected if detected else Path.cwd().resolve()

    # Look up packet
    pkt_info = _lookup_packet(conn, args.id)
    if not pkt_info:
        print(f"Error: Packet '{args.id}' not found.", file=sys.stderr)
        return 1

    pkt_id, pkt_hash, body_raw = pkt_info
    try:
        body_dict = parse_canonical_json(body_raw)
        packet = Packet.model_validate(body_dict)
    except Exception as exc:
        print(f"Error: Failed to parse packet '{pkt_id}': {exc}", file=sys.stderr)
        return 1

    report = check_staleness(
        packet=packet,
        repo_root=repo_root,
        conn=conn,
        key_bytes=key_bytes,
        packet_hash_val=pkt_hash,
    )

    if args.json:
        drifts_json = [
            {
                "path": d.path,
                "drift_type": d.drift_type.value,
                "expected_hash": d.expected_hash,
                "current_hash": d.current_hash,
                "new_path": d.new_path,
            }
            for d in report.drifts
        ]
        out_dict: dict[str, Any] = {
            "packet_id": pkt_id,
            "packet_hash": pkt_hash,
            "is_stale": report.is_stale,
            "is_critical": report.is_critical,
            "is_git_repo": report.is_git_repo,
            "head_commit": report.head_commit,
            "packet_commit": report.packet_commit,
            "acknowledged": report.acknowledged,
            "drift_hash": report.drift_hash,
            "detail": report.detail,
            "drifts": drifts_json,
        }
        print(json.dumps(out_dict, indent=2))
        return 0

    # Human-readable CLI output
    status_str = "STALE (drifted)" if report.is_stale else "FRESH (in sync)"
    if not report.is_git_repo:
        status_str = "NOT A GIT REPOSITORY"
    elif report.detail and "No repo_state" in report.detail:
        status_str = "NO REPO STATE RECORDED"

    print(f"Packet:      {pkt_id} ({pkt_hash[:12]})")
    print(f"Status:      {status_str}")
    if report.packet_commit:
        print(f"Base commit: {report.packet_commit[:12]}")
    if report.head_commit:
        print(f"HEAD commit: {report.head_commit[:12]}")

    if report.drifts:
        print(f"\nDrifted referenced files ({len(report.drifts)}):")
        for d in report.drifts:
            extra = f" -> {d.new_path}" if d.new_path else ""
            print(f"  - {d.path}: {d.drift_type.value}{extra}")

    if report.acknowledged:
        print("\nNotice: Acknowledgment active. MCP load allowed despite drift.")
    elif report.is_critical:
        print("\nWarning: Critical drift detected! MCP load will be blocked.")
        print(f"Use 'swallo approve {pkt_id} --target <target> --ack-stale' to allow.")

    return 0
