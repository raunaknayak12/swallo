"""
Implementation of the 'swallo log' command with cryptographic chain verification.

Per TRD.md section 5.1, IMPLEMENTATION_PLAN.md Step 4, and Security.md F10:
- Displays recent tamper-evident audit events.
- Flag --verify checks HMAC continuity across every event row to detect
  modification, deletion, or tampering.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from swallo.config import get_store_dir
from swallo.errors import IntegrityError, UsageError
from swallo.store.db import get_connection, get_or_create_local_key
from swallo.store.eventlog import list_events
from swallo.store.eventlog import verify as verify_eventlog


def run_log(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="swallo log",
        description="Inspect and verify the tamper-evident audit event log.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Traverse and cryptographically verify the integrity of the HMAC hash chain.",
    )
    parser.add_argument(
        "--limit",
        "-n",
        type=int,
        default=25,
        help="Maximum number of log events to display (default: 25).",
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

    # 1. Cryptographic chain verification
    if args.verify:
        errors = verify_eventlog(conn, key_bytes)
        if errors:
            if args.json:
                print(json.dumps({"verified": False, "errors": errors}, indent=2))
            else:
                msg = (
                    f"FAILED: Tamper-evident event log verification failed with "
                    f"{len(errors)} error(s):"
                )
                print(msg, file=sys.stderr)
                for err in errors:
                    print(f"  - {err}", file=sys.stderr)
            return IntegrityError.exit_code

        if args.json:
            print(json.dumps({"verified": True, "errors": []}, indent=2))
        else:
            print(
                "OK: Event log cryptographic hash chain verified successfully. "
                "Zero tampering detected."
            )
        return 0

    # 2. List recent events
    events = list_events(conn, limit=args.limit)

    if args.json:
        print(json.dumps({"events": events}, indent=2))
        return 0

    print("================================================================================")
    print("                           SWALLO AUDIT EVENT LOG                               ")
    print("================================================================================")
    if not events:
        print("  (Log is empty)")
    for ev in events:
        seq = ev["seq"]
        ts = ev["ts"]
        ev_type = ev["type"]
        pkt = ev["packet_hash"] or "-"
        detail = ev["detail"] or ""
        print(f"#{seq:03d} | {ts} | {ev_type:16} | pkt: {pkt[:16]}... | {detail}")

    print("================================================================================")
    return 0
