"""
Implementation of the 'swallo breaker' command.

Per TRD.md section 11, CLI_AND_MCP_SPEC.md section 1, and ADR-028:
- Inspects or resets circuit breaker state for MCP sessions.
- Sessions are paused after repeated blocked save attempts (e.g. secret detection).
- Reset operation requires controlling terminal confirmation unless --force is provided.
- Reset events are recorded in the tamper-evident audit log.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from swallo.config import get_store_dir
from swallo.errors import UsageError
from swallo.server.guards import CircuitBreaker
from swallo.store.db import get_connection, get_or_create_local_key
from swallo.store.eventlog import append as log_event
from swallo.terminal import confirm_on_terminal


def run_breaker(argv: list[str]) -> int:
    """Entry point for 'swallo breaker' command."""
    parser = argparse.ArgumentParser(
        prog="swallo breaker",
        description="Show or reset paused MCP sessions.",
    )
    parser.add_argument(
        "action",
        choices=["status", "reset"],
        help="Action to perform: 'status' to view sessions, 'reset' to clear trips.",
    )
    parser.add_argument(
        "--session",
        default=None,
        help="Target a specific session ID (defaults to all sessions).",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Bypass interactive confirmation prompt when resetting.",
    )
    parser.add_argument("--store", type=Path, default=None, help="Store directory override.")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON.")

    args = parser.parse_args(argv)

    store_dir = (args.store or get_store_dir()).resolve()
    db_path = store_dir / "swallo.db"
    key_path = store_dir / "key"

    if not db_path.exists():
        raise UsageError(f"Store at '{store_dir}' not initialized.")

    conn = get_connection(db_path)

    if args.action == "status":
        records = CircuitBreaker.get_status(conn, session_id=args.session)
        if args.json:
            print(json.dumps(records, indent=2))
            return 0

        if not records:
            print("No MCP session circuit breaker records found.")
            return 0

        print(f"{'SESSION ID':<36} {'BLOCKED':<8} {'STATUS':<10} {'TRIPPED UNTIL'}")
        print("-" * 75)
        for r in records:
            status_label = "PAUSED" if r["is_tripped"] else "ACTIVE"
            tripped_until = r["tripped_until"] or "-"
            print(
                f"{r['session_id']:<36} "
                f"{r['blocked_count']:<8} "
                f"{status_label:<10} "
                f"{tripped_until}"
            )
        return 0

    if args.action == "reset":
        if not args.force:
            target_str = f"session '{args.session}'" if args.session else "all sessions"
            prompt = f"Are you sure you want to reset the circuit breaker for {target_str}? [y/N]: "
            if not confirm_on_terminal(prompt):
                print("Reset aborted by user.", file=sys.stderr)
                return 1

        reset_count = CircuitBreaker.reset(conn, session_id=args.session)

        # Log reset to tamper-evident audit event log if local key is available
        if key_path.exists():
            key_bytes = get_or_create_local_key(key_path)
            log_event(
                conn,
                key_bytes,
                type="breaker_reset",
                detail=f"Reset {reset_count} session(s)" + (
                    f" (target: {args.session})" if args.session else ""
                ),
            )

        if args.json:
            print(json.dumps({
                "action": "reset",
                "session": args.session,
                "reset_count": reset_count,
            }))
        else:
            target_str = f" for session '{args.session}'" if args.session else ""
            print(f"Circuit breaker reset{target_str} ({reset_count} record(s) cleared).")

        return 0

    return 0
