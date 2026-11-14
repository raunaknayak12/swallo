"""
Implementation of the 'swallo import' command.

Per TRD.md section 6.1, CLI_AND_MCP_SPEC.md section 1, and COMMANDS.md:
- Imports conversation sessions from vendor exports (ChatGPT, Claude, Gemini Takeout).
- Streams safely with ArchiveGuard and safe_json_loads.
- Lists available sessions with --list-sessions or selects via --select / --session.
- Ingests packets with origin='imported' and runs redaction engine before persistence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Literal

from swallo.capture.importers.base import BaseImporter
from swallo.capture.importers.chatgpt import ChatGPTImporter
from swallo.capture.importers.claude_export import ClaudeImporter
from swallo.capture.importers.gemini_takeout import GeminiTakeoutImporter
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
)
from swallo.schema.models import Packet
from swallo.store.db import get_connection, get_or_create_local_key
from swallo.store.eventlog import append as log_event
from swallo.store.objects import ObjectStore

_IMPORTER_REGISTRY: dict[str, type[BaseImporter]] = {
    "chatgpt": ChatGPTImporter,
    "claude": ClaudeImporter,
    "gemini": GeminiTakeoutImporter,
}


def _get_importer(vendor: str, config_dir: Path | None = None) -> BaseImporter:
    """Instantiate importer instance with configured safety settings."""
    cfg, _ = load_config(config_dir)
    cls = _IMPORTER_REGISTRY.get(vendor.lower())
    if not cls:
        valid_vendors = ", ".join(sorted(_IMPORTER_REGISTRY.keys()))
        raise UsageError(
            f"Unsupported vendor '{vendor}'. Available importers: {valid_vendors}."
        )
    return cls(settings=cfg.importer)


def run_import(argv: list[str]) -> int:
    """Entry point for 'swallo import'."""
    parser = argparse.ArgumentParser(
        prog="swallo import",
        description="Import sessions from a ChatGPT, Claude, or Gemini data export archive.",
    )
    parser.add_argument(
        "vendor",
        choices=["chatgpt", "claude", "gemini"],
        help="Vendor export format (chatgpt, claude, or gemini).",
    )
    parser.add_argument(
        "archive",
        type=Path,
        help="Path to archive (.zip) or JSON file.",
    )
    parser.add_argument(
        "--list-sessions",
        action="store_true",
        help="List available conversation sessions in the archive and exit.",
    )
    parser.add_argument(
        "--select",
        action="store_true",
        help="Interactively select a session from the archive to import.",
    )
    parser.add_argument(
        "--session",
        type=str,
        default=None,
        help="Specific conversation session ID to import.",
    )
    parser.add_argument(
        "--project",
        default="default",
        help="Target project name for imported packets (default: default).",
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

    archive_path = args.archive.resolve()
    if not archive_path.exists():
        raise UsageError(f"Archive file not found: {archive_path}")

    store_dir = (args.store or get_store_dir()).resolve()
    importer = _get_importer(args.vendor, config_dir=store_dir)

    # 1. Handle --list-sessions
    if args.list_sessions:
        sessions = importer.list_sessions(archive_path)
        if args.json:
            payload = [
                {
                    "id": s.id,
                    "title": s.title,
                    "message_count": s.message_count,
                    "created_at": s.created_at,
                    "updated_at": s.updated_at,
                }
                for s in sessions
            ]
            print(json.dumps(payload, indent=2))
        else:
            print(f"Sessions in '{archive_path.name}':")
            for idx, s in enumerate(sessions):
                print(f"[{idx + 1}] ID: {s.id}")
                print(f"    Title:    {s.title}")
                print(f"    Messages: {s.message_count}")
                print(f"    Created:  {s.created_at}")
        return 0

    # 2. Collect packets to ingest
    packets_to_save: list[Packet] = []

    if args.session:
        pkt = importer.extract_session(archive_path, args.session, project=args.project)
        packets_to_save.append(pkt)
    elif args.select:
        sessions = importer.list_sessions(archive_path)
        if not sessions:
            raise ValidationError(f"No conversation sessions found in '{archive_path.name}'.")

        selected_id = sessions[0].id
        if sys.stdin.isatty():
            print(f"Available sessions in '{archive_path.name}':")
            for idx, s in enumerate(sessions):
                print(f"  [{idx + 1}] {s.id}: {s.title} ({s.message_count} messages)")
            choice = input("Select session number [1]: ").strip()
            if choice:
                try:
                    c_idx = int(choice) - 1
                    if 0 <= c_idx < len(sessions):
                        selected_id = sessions[c_idx].id
                except ValueError:
                    # Non-integer selection; default to the first session
                    pass
        pkt = importer.extract_session(archive_path, selected_id, project=args.project)
        packets_to_save.append(pkt)
    else:
        # Extract all sessions
        packets_to_save = importer.extract_all(archive_path, project=args.project)
        if not packets_to_save:
            raise ValidationError(f"No conversation sessions extracted from '{archive_path.name}'.")

    # 3. Initialize store and key
    db_path = store_dir / "swallo.db"
    key_path = store_dir / "key"
    if not db_path.exists() or not key_path.exists():
        raise UsageError(f"Store at '{store_dir}' is not initialized. Run 'swallo init' first.")

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

    conn = get_connection(db_path)
    obj_store = ObjectStore(store_dir)
    imported_results: list[dict[str, object]] = []

    for pkt in packets_to_save:
        pkt_dict = pkt.model_dump(exclude_none=True)

        # Redact goal
        try:
            if "goal" in pkt_dict and isinstance(pkt_dict["goal"], dict):
                g_text = pkt_dict["goal"].get("text", "")
                if g_text:
                    r = engine.redact(g_text, mode=mode, key=key_bytes)
                    pkt_dict["goal"]["text"] = r.text

            # Redact items
            for item in pkt_dict.get("items", []):
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

        # Compute hash and ID
        h_form = hashed_form(pkt_dict)
        calculated_hash = packet_hash(h_form)
        derived_id = derive_packet_id(calculated_hash)
        pkt_dict["id"] = derived_id

        canonical_body = canonicalize(pkt_dict)
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
                    pkt.schema_version,
                    pkt.project,
                    pkt.parent,
                    pkt.created_at,
                    canonical_body,
                    "imported",
                    None,
                ),
            )
        finally:
            cursor.close()

        log_event(
            conn,
            key_bytes,
            type="packet_imported",
            packet_hash=calculated_hash,
            detail=f"Imported packet {derived_id} from {args.vendor}",
        )

        imported_results.append(
            {
                "status": "imported",
                "id": derived_id,
                "hash": calculated_hash,
                "project": pkt.project,
                "item_count": len(pkt.items),
                "origin": "imported",
            }
        )

    if args.json:
        print(json.dumps(imported_results, indent=2))
    else:
        print(f"Successfully imported {len(imported_results)} packet(s) from {args.vendor}:")
        for res in imported_results:
            print(f"  ID:      {res['id']}")
            print(f"  Hash:    {res['hash']}")
            print(f"  Project: {res['project']}")
            print(f"  Items:   {res['item_count']}")

    return 0
