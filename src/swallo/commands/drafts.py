"""
Implementation of the 'swallo drafts' command.

Per TRD.md section 8, CLI_AND_MCP_SPEC.md section 1, and ADR-007:
- Lists or purges unapproved agent drafts.
- Strictly CLI-only: agents cannot call this via MCP.
- Never touches approved packets or referenced packets.
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from swallo.config import get_store_dir
from swallo.errors import UsageError
from swallo.schema.canonical import parse_canonical_json
from swallo.store.db import get_connection
from swallo.terminal import confirm_on_terminal

_logger = logging.getLogger(__name__)


def _extract_session_id(body_raw: object) -> str | None:
    """Extract session_id from packet sources metadata in canonical body."""
    if isinstance(body_raw, (bytes, memoryview)):
        body_str = bytes(body_raw).decode("utf-8", errors="replace")
    else:
        body_str = str(body_raw)
    try:
        data = parse_canonical_json(body_str)
        if isinstance(data, dict):
            sources = data.get("sources")
            if isinstance(sources, list) and sources and isinstance(sources[0], dict):
                sid = sources[0].get("session_id")
                return str(sid) if sid else None
    except Exception as exc:
        _logger.debug("Failed to extract session_id from packet body: %s", exc)
    return None


def _get_drafts_query(
    conn: sqlite3.Connection,
    older_than_days: float | None = None,
    session_id: str | None = None,
    project: str | None = None,
) -> list[dict[str, object]]:
    """Retrieve unapproved drafts matching criteria."""
    query = """
        SELECT id, hash, project, created_at, expires_at, LENGTH(body), body
        FROM packets
        WHERE hash NOT IN (SELECT packet_hash FROM approvals)
    """
    params: list[object] = []

    if project:
        query += " AND project = ?"
        params.append(project)

    if older_than_days is not None:
        threshold = (datetime.now(UTC) - timedelta(days=older_than_days)).isoformat()
        query += " AND created_at <= ?"
        params.append(threshold)

    query += " ORDER BY created_at DESC"

    cursor = conn.cursor()
    try:
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        drafts: list[dict[str, object]] = []
        for r in rows:
            extracted_sid = _extract_session_id(r[6])
            if session_id and extracted_sid != session_id:
                continue
            drafts.append({
                "id": str(r[0]),
                "hash": str(r[1]),
                "project": str(r[2]),
                "session_id": extracted_sid,
                "created_at": str(r[3]),
                "expires_at": str(r[4]) if r[4] else None,
                "bytes": int(r[5]),
            })
        return drafts
    finally:
        cursor.close()


def run_drafts(argv: list[str]) -> int:
    """Entry point for 'swallo drafts' command."""
    parser = argparse.ArgumentParser(
        prog="swallo drafts",
        description="Review or purge unapproved agent drafts.",
    )
    parser.add_argument(
        "action",
        choices=["list", "purge"],
        help="Action to perform: 'list' to view unapproved drafts, 'purge' to remove them.",
    )
    parser.add_argument(
        "--older-than",
        type=float,
        default=None,
        metavar="DAYS",
        help="Target drafts older than DAYS (e.g. 1, 7).",
    )
    parser.add_argument(
        "--session",
        default=None,
        help="Target drafts from a specific MCP session ID.",
    )
    parser.add_argument(
        "--project",
        default=None,
        help="Target drafts from a specific project.",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Bypass interactive terminal confirmation when purging.",
    )
    parser.add_argument("--store", type=Path, default=None, help="Store directory override.")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON.")

    args = parser.parse_args(argv)

    store_dir = (args.store or get_store_dir()).resolve()
    db_path = store_dir / "swallo.db"

    if not db_path.exists():
        raise UsageError(f"Store at '{store_dir}' not initialized.")

    conn = get_connection(db_path)

    if args.action == "list":
        drafts = _get_drafts_query(
            conn,
            older_than_days=args.older_than,
            session_id=args.session,
            project=args.project,
        )
        if args.json:
            print(json.dumps(drafts, indent=2))
            return 0

        if not drafts:
            print("No unapproved drafts found.")
            return 0

        print(f"{'DRAFT ID':<16} {'CREATED':<20} {'BYTES':<8} {'PROJECT':<14} {'SESSION'}")
        print("-" * 75)
        for d in drafts:
            session_display = str(d["session_id"] or "-")[:20]
            print(
                f"{str(d['id']):<16} "
                f"{str(d['created_at'])[:19]:<20} "
                f"{d['bytes']:<8} "
                f"{str(d['project']):<14} "
                f"{session_display}"
            )
        print(f"\nTotal: {len(drafts)} unapproved draft(s).")
        return 0

    if args.action == "purge":
        target_drafts = _get_drafts_query(
            conn,
            older_than_days=args.older_than,
            session_id=args.session,
            project=args.project,
        )

        if not target_drafts:
            if args.json:
                print(json.dumps({"purged_count": 0, "draft_ids": []}))
            else:
                print("No unapproved drafts matched criteria for purge.")
            return 0

        if not args.force:
            prompt = f"Purge {len(target_drafts)} unapproved draft(s)? [y/N]: "
            if not confirm_on_terminal(prompt):
                print("Purge aborted by user.", file=sys.stderr)
                return 1

        draft_ids = [str(d["id"]) for d in target_drafts]
        cursor = conn.cursor()
        deleted_count = 0
        try:
            for d_id in draft_ids:
                cursor.execute(
                    """
                    DELETE FROM packets
                    WHERE id = ?
                      AND hash NOT IN (SELECT packet_hash FROM approvals)
                    """,
                    (d_id,),
                )
                deleted_count += cursor.rowcount
        finally:
            cursor.close()

        if args.json:
            print(json.dumps({
                "purged_count": deleted_count,
                "draft_ids": draft_ids,
            }))
        else:
            print(f"Purged {deleted_count} unapproved draft(s).")

        return 0

    return 0
