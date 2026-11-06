"""
Implementation of the 'swallo edit' command.

Per TRD.md section 7, CLI_AND_MCP_SPEC.md section 1, and COMMANDS.md section 4:
- Opens a draft packet's contents in the user's $EDITOR.
- Validates the edited JSON schema upon exit.
- Generates a new revision ID and stores it as an unapproved packet.
- Logs the revision in the tamper-evident audit event log.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from swallo.config import get_store_dir
from swallo.errors import UsageError
from swallo.schema.canonical import (
    canonicalize,
    derive_packet_id,
    packet_hash,
    parse_canonical_json,
)
from swallo.schema.models import Packet
from swallo.store.db import get_connection, get_or_create_local_key
from swallo.store.eventlog import append as log_event


def _get_editor_command() -> list[str]:
    """Determine the editor command based on environment and platform."""
    env_editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if env_editor:
        return [env_editor]
    if sys.platform == "win32":
        notepad = shutil.which("notepad")
        return [notepad] if notepad else ["notepad.exe"]
    for fallback in ["nano", "vim", "vi"]:
        found = shutil.which(fallback)
        if found:
            return [found]
    return ["nano"]


def run_edit(argv: list[str]) -> int:
    """Entry point for 'swallo edit'."""
    parser = argparse.ArgumentParser(
        prog="swallo edit",
        description="Edit a draft packet in $EDITOR to create a new revision.",
    )
    parser.add_argument("id", metavar="ID", help="Packet ID or hash to edit.")
    parser.add_argument("--store", type=Path, default=None, help="Store directory override.")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON.")

    args = parser.parse_args(argv)

    store_dir = (args.store or get_store_dir()).resolve()
    db_path = store_dir / "swallo.db"
    key_path = store_dir / "key"

    if not db_path.exists():
        raise UsageError(f"Store at '{store_dir}' not initialized.")

    conn = get_connection(db_path)

    # 1. Look up packet
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, hash, body, project, session_id FROM packets
            WHERE id = ? OR id LIKE ? OR hash = ? OR hash LIKE ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (args.id, f"{args.id}%", args.id, f"{args.id}%"),
        )
        row = cur.fetchone()
    finally:
        cur.close()

    if not row:
        print(f"Error: Packet '{args.id}' not found.", file=sys.stderr)
        return 1

    orig_id, _orig_hash, orig_body_raw, project, session_id = (
        str(row[0]),
        str(row[1]),
        str(row[2]),
        str(row[3]),
        str(row[4]) if row[4] else None,
    )

    try:
        orig_dict = parse_canonical_json(orig_body_raw)
    except Exception as exc:
        print(f"Error: Existing packet '{orig_id}' has malformed body: {exc}", file=sys.stderr)
        return 1

    # Pretty-printed JSON for editing
    formatted_original = json.dumps(orig_dict, indent=2, ensure_ascii=False)

    # Write to a secure temporary file
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        encoding="utf-8",
        delete=False,
    ) as tmp_file:
        tmp_file.write(formatted_original)
        tmp_path = Path(tmp_file.name)

    try:
        editor_cmd = _get_editor_command()
        cmd = [*editor_cmd, str(tmp_path)]
        try:
            res = subprocess.run(cmd, timeout=300, check=False)  # noqa: S603
            if res.returncode != 0:
                print(f"Error: Editor exited with code {res.returncode}.", file=sys.stderr)
                return 1
        except subprocess.TimeoutExpired:
            print("Error: Editor session timed out.", file=sys.stderr)
            return 1

        edited_raw = tmp_path.read_text(encoding="utf-8")
        if edited_raw.strip() == formatted_original.strip():
            print("No changes made.")
            return 0

        # Validate edited JSON and schema
        try:
            edited_dict = parse_canonical_json(edited_raw)
            if not isinstance(edited_dict, dict):
                raise ValueError("Edited JSON must be an object.")
            packet = Packet.model_validate(edited_dict)
        except Exception as exc:
            print(f"Error: Edited content is invalid: {exc}", file=sys.stderr)
            return 1

        # Canonicalize and derive new identifiers
        pkt_dict = packet.model_dump()
        new_hash = packet_hash(pkt_dict)
        new_id = derive_packet_id(new_hash)
        canonical_bytes = canonicalize(pkt_dict)
        now_iso = datetime.now(UTC).isoformat()

        # Insert new packet revision
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT OR REPLACE INTO packets (
                    id, hash, project, session_id, created_at, expires_at, origin, body
                )
                VALUES (?, ?, ?, ?, ?, NULL, 'cli', ?)
                """,
                (new_id, new_hash, project, session_id, now_iso, canonical_bytes.decode("utf-8")),
            )
        finally:
            cursor.close()

        # Log edit event
        if key_path.exists():
            key_bytes = get_or_create_local_key(key_path)
            log_event(
                conn,
                key_bytes,
                type="packet_edit",
                packet_hash=new_hash,
                detail=f"Created revision {new_id} from {orig_id}",
            )

        if args.json:
            out_obj: dict[str, Any] = {
                "status": "revised",
                "original_id": orig_id,
                "id": new_id,
                "hash": new_hash,
                "project": project,
            }
            print(json.dumps(out_obj, indent=2))
        else:
            print(f"Created new revision '{new_id}' (hash: {new_hash[:12]}).")

        return 0

    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
