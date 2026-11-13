"""
Implementation of the 'swallo show' command with risk-first review summary.

Per ADR-021, TRD.md section 7.1, and IMPLEMENTATION_PLAN.md Step 4:
- Displays a tool-generated risk summary before any packet contents:
  - Invisible / zero-width characters detected.
  - Shell command snippets / execution patterns.
  - URLs and external links.
  - Opaque, high-entropy blobs.
  - Approval state across target IDEs.
- Never copies risk flags from packet text; generates them dynamically.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from swallo.adapters.registry import list_supported_targets
from swallo.config import get_store_dir
from swallo.errors import UsageError
from swallo.redact.decode import OpaqueBlobDetector
from swallo.render.sanitize import flag_invisible, sanitize_for_display
from swallo.schema.canonical import parse_canonical_json
from swallo.store.db import get_connection, get_or_create_local_key
from swallo.store.ledger import is_approved

_CMD_PATTERN = re.compile(
    r"(?m)^\s*(?:\$\s+|\b(?:sudo|rm\s+-rf|chmod|curl|wget|bash|sh|python|powershell)\b)"
)
_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+")


def _scan_risks(packet_data: dict[str, object]) -> dict[str, list[str]]:
    """Scan packet fields and compile a dynamic security risk summary."""
    invisible_flags: list[str] = []
    commands: list[str] = []
    urls: list[str] = []
    opaque_blobs: list[str] = []

    blob_detector = OpaqueBlobDetector(min_length=60, min_entropy=4.5)

    texts_to_scan: list[str] = []
    goal = packet_data.get("goal")
    if isinstance(goal, dict):
        text_val = goal.get("text")
        if isinstance(text_val, str):
            texts_to_scan.append(text_val)

    items = packet_data.get("items")
    if isinstance(items, list):
        for it in items:
            if isinstance(it, dict):
                text_val = it.get("text")
                if isinstance(text_val, str):
                    texts_to_scan.append(text_val)

    for text in texts_to_scan:
        # 1. Invisible characters
        invisible_flags.extend(flag_invisible(text))

        # 2. Commands / shell execution
        for m in _CMD_PATTERN.finditer(text):
            nl = text.find("\n", m.start())
            line = text[m.start() : nl] if nl != -1 else text[m.start() :]
            commands.append(line.strip())

        # 3. URLs
        for m in _URL_PATTERN.finditer(text):
            urls.append(m.group(0))

        # 4. Opaque blobs
        for f in blob_detector.scan(text):
            opaque_blobs.append(f.matched_text[:24] + "...")

    return {
        "invisible_characters": invisible_flags,
        "command_lines": commands,
        "urls": urls,
        "opaque_blobs": opaque_blobs,
    }


def run_show(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="swallo show",
        description="Display a context packet with a risk-first security summary.",
    )
    parser.add_argument("packet_id", help="Packet identifier (e.g. pkt_...) or hash.")
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

    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, hash, schema_version, project, created_at, body
            FROM packets WHERE id = ? OR hash = ?
            """,
            (args.packet_id, args.packet_id),
        )
        row = cursor.fetchone()
    finally:
        cursor.close()

    if not row:
        raise UsageError(f"Packet '{args.packet_id}' not found in store.")

    pkt_id, pkt_hash, schema_ver, project, created_at, body_blob = (
        row[0],
        row[1],
        row[2],
        row[3],
        row[4],
        row[5],
    )
    parsed = parse_canonical_json(body_blob)
    if not isinstance(parsed, dict):
        raise UsageError(f"Corrupted packet body in store for {pkt_id}")
    packet_dict = parsed

    # Approvals check
    known_targets = list_supported_targets()
    approvals_status = {
        tgt: is_approved(conn, key_bytes, pkt_hash, tgt) for tgt in known_targets
    }

    # Backward compatibility aliases for JSON output:
    # 0.1.2 consumers / tests expect 'claude_code' and legacy targets like 'cursor'
    json_approvals = dict(approvals_status)
    if "claude-code" in json_approvals:
        json_approvals["claude_code"] = json_approvals["claude-code"]
    if "cursor" not in json_approvals:
        json_approvals["cursor"] = is_approved(conn, key_bytes, pkt_hash, "cursor")

    # Generate risks
    risks = _scan_risks(packet_dict)

    if args.json:
        out = {
            "id": pkt_id,
            "hash": pkt_hash,
            "schema_version": schema_ver,
            "project": project,
            "created_at": created_at,
            "approvals": json_approvals,
            "risk_summary": risks,
            "packet": packet_dict,
        }
        print(json.dumps(out, indent=2))
        return 0

    # Human-readable output: RISKS FIRST per ADR-021
    print("================================================================================")
    print("                      SWALLO RISK-FIRST SECURITY SUMMARY                        ")
    print("================================================================================")
    has_risks = any(bool(v) for v in risks.values())
    if not has_risks:
        print("  [OK] No anomalous command patterns, URLs, invisible chars or opaque blobs.")
    else:
        if risks["invisible_characters"]:
            count = len(risks["invisible_characters"])
            print(f"  [WARN] Invisible / Zero-Width Characters ({count}):")
            for inv in risks["invisible_characters"][:5]:
                print(f"         - {inv}")
        if risks["command_lines"]:
            print(f"  [WARN] Shell / Command Patterns ({len(risks['command_lines'])}):")
            for cmd in risks["command_lines"][:5]:
                print(f"         - {cmd}")
        if risks["urls"]:
            print(f"  [WARN] External URLs ({len(risks['urls'])}):")
            for u in risks["urls"][:5]:
                print(f"         - {u}")
        if risks["opaque_blobs"]:
            print(f"  [WARN] Opaque / High-Entropy Blobs ({len(risks['opaque_blobs'])}):")
            for b in risks["opaque_blobs"][:5]:
                print(f"         - {b}")

    print("\nTarget Approvals:")
    for tgt, approved in approvals_status.items():
        badge = "[APPROVED]" if approved else "[NOT APPROVED]"
        print(f"  {badge:15} {tgt}")

    print("================================================================================")
    print(f"Packet ID:    {pkt_id}")
    print(f"Hash:         {pkt_hash}")
    print(f"Project:      {project}")
    print(f"Created:      {created_at}")

    goal = packet_dict.get("goal")
    if isinstance(goal, dict):
        goal_text = str(goal.get("text", ""))
        print(f"\nGoal: {sanitize_for_display(goal_text)}")

    items = packet_dict.get("items", [])
    if isinstance(items, list):
        print(f"\nItems ({len(items)}):")
        for i, item in enumerate(items, 1):
            if isinstance(item, dict):
                kind = str(item.get("kind", "item")).upper()
                text = sanitize_for_display(str(item.get("text", "")))
                print(f"  {i:2d}. [{kind:12}] {text}")

    print("================================================================================")
    return 0
