"""
Implementation of the 'swallo save' command.

Per TRD.md section 6, IMPLEMENTATION_PLAN.md Step 4, and PACKET_SCHEMA.md:
- Ingests context packets from a file or standard input.
- Validates structure against Pydantic Packet schema and bounds.
- Runs redaction pipeline (patterns, entropy, denylist, decoded variants).
- Stores packet bytes in SQLite packets table and content-addressed object store.
- Appends event to tamper-evident audit log.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Literal

from swallo.config import get_store_dir, load_config
from swallo.errors import RedactionBlockedError, UsageError, ValidationError
from swallo.redact.decode import DecodedVariantDetector
from swallo.redact.denylist import DenylistDetector
from swallo.redact.engine import RedactionEngine
from swallo.redact.entropy import EntropyDetector
from swallo.redact.patterns import PatternDetector
from swallo.schema.canonical import (
    canonicalize,
    derive_packet_id,
    hashed_form,
    packet_hash,
    parse_canonical_json,
)
from swallo.schema.models import Packet
from swallo.store.db import get_connection, get_or_create_local_key
from swallo.store.eventlog import append as log_event
from swallo.store.objects import ObjectStore


def run_save(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="swallo save",
        description="Validate, redact, and store a context packet from file or stdin.",
    )
    parser.add_argument(
        "file",
        nargs="?",
        default="-",
        help="Path to JSON packet file, or '-' to read from standard input.",
    )
    parser.add_argument(
        "--store",
        type=Path,
        default=None,
        help="Store directory override.",
    )
    parser.add_argument(
        "--fail-closed",
        action="store_true",
        help="Abort if any secret patterns or credentials are detected.",
    )
    parser.add_argument(
        "--warn",
        action="store_true",
        help="Redact sensitive secrets with placeholders even if config defaults to fail-closed.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON.",
    )

    args = parser.parse_args(argv)

    store_dir = (args.store or get_store_dir()).resolve()
    db_path = store_dir / "swallo.db"
    key_path = store_dir / "key"

    if not db_path.exists() or not key_path.exists():
        msg = f"Store at '{store_dir}' is not initialized. Run 'swallo init' first."
        if args.json:
            print(json.dumps({"error": msg, "status": "uninitialized"}))
        else:
            print(f"Error: {msg}", file=sys.stderr)
        return UsageError.exit_code

    # 1. Read input JSON
    if args.file == "-":
        raw_text = sys.stdin.read()
    else:
        path = Path(args.file)
        if not path.exists():
            raise UsageError(f"Input file not found: {path}")
        raw_text = path.read_text(encoding="utf-8")

    if not raw_text.strip():
        raise ValidationError("Input packet JSON cannot be empty.")

    data = parse_canonical_json(raw_text)

    # 2. Validate against Packet schema
    packet = Packet.model_validate(data)
    packet_dict = packet.model_dump()

    # 3. Redact sensitive content
    key_bytes = get_or_create_local_key(key_path)
    cfg, _ = load_config(store_dir)

    mode: Literal["fail_closed", "warn"]
    if args.warn:
        mode = "warn"
    elif args.fail_closed:
        mode = "fail_closed"
    else:
        mode = "fail_closed" if cfg.redact.mode == "fail_closed" else "warn"

    patterns = PatternDetector()
    entropy = EntropyDetector(threshold=4.3)
    denylist = DenylistDetector(cfg.redact.denylist)
    decoded = DecodedVariantDetector(inner_detectors=[patterns, entropy])

    engine = RedactionEngine([patterns, entropy, denylist, decoded])

    # Redact goal text
    try:
        if packet_dict.get("goal") and isinstance(packet_dict["goal"], dict):
            goal_text = packet_dict["goal"].get("text", "")
            if goal_text:
                r = engine.redact(goal_text, mode=mode, key=key_bytes)
                packet_dict["goal"]["text"] = r.text

        # Redact items
        for item in packet_dict.get("items", []):
            if isinstance(item, dict) and "text" in item:
                r = engine.redact(item["text"], mode=mode, key=key_bytes)
                item["text"] = r.text
    except RedactionBlockedError as e:
        if args.json:
            print(
                json.dumps(
                    {
                        "error": str(e),
                        "status": "blocked",
                        "exit_code": RedactionBlockedError.exit_code,
                    }
                )
            )
        else:
            print(f"Error: {e}", file=sys.stderr)
        return RedactionBlockedError.exit_code

    # 4. Compute hash and derive ID
    h_form = hashed_form(packet_dict)
    calculated_hash = packet_hash(h_form)
    derived_id = derive_packet_id(calculated_hash)
    packet_dict["id"] = derived_id

    canonical_body = canonicalize(packet_dict)

    # 5. Persist to SQLite and Object Store
    conn = get_connection(db_path)
    obj_store = ObjectStore(store_dir)
    obj_store.put(canonical_body)

    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT OR REPLACE INTO packets
            (id, hash, schema_version, project, parent, created_at, body, origin, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                derived_id,
                calculated_hash,
                packet.schema_version,
                packet.project,
                packet.parent,
                packet.created_at,
                canonical_body,
                "cli_save",
                None,
            ),
        )
    finally:
        cursor.close()

    # 6. Log audit event
    log_event(
        conn,
        key_bytes,
        type="packet_saved",
        packet_hash=calculated_hash,
        detail=f"Saved packet {derived_id} for project {packet.project}",
    )

    result_data = {
        "status": "saved",
        "id": derived_id,
        "hash": calculated_hash,
        "project": packet.project,
        "item_count": len(packet.items),
    }

    if args.json:
        print(json.dumps(result_data, indent=2))
    else:
        print("Packet saved successfully:")
        print(f"  ID:      {derived_id}")
        print(f"  Hash:    {calculated_hash}")
        print(f"  Project: {packet.project}")
        print(f"  Items:   {len(packet.items)}")

    return 0
