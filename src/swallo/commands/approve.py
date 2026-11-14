"""
Implementation of the 'swallo approve' command.

Per ADR-003, ADR-007, IMPLEMENTATION_PLAN.md Step 4, and Security.md F2/F21:
- Approval state lives in the local cryptographic ledger, keyed by (packet_hash, target).
- Requires interactive confirmation on the controlling terminal (/dev/tty or CONIN$).
  There is NO --force flag; the TTY barrier cannot be bypassed at the CLI level.
- There is NO approve tool in the MCP server; approval MUST be triggered via the CLI.
- Optional passphrase signing (Ed25519) via swallo[sign] when signing mode is enabled.

IMPORTANT: Tests must inject `_confirm_stream_in` via monkeypatching `confirm_on_terminal`
  or via the `stream_in=` / `stream_out=` arguments to `confirm_on_terminal`. The --force
  CLI flag does NOT exist; removing it closes the production-reachable TTY-bypass path.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from swallo.adapters.registry import list_supported_targets, normalize_target
from swallo.config import get_store_dir, load_config
from swallo.errors import UsageError
from swallo.repo.gitstate import get_repo_root
from swallo.repo.staleness import check_staleness, record_stale_ack
from swallo.schema.canonical import parse_canonical_json
from swallo.schema.models import Packet
from swallo.store.db import get_connection, get_or_create_local_key
from swallo.store.ledger import approve
from swallo.terminal import confirm_on_terminal


def run_approve(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="swallo approve",
        description="Grant human approval for a packet to be delivered to a specific IDE target.",
    )
    parser.add_argument("packet_id", help="Packet identifier (pkt_...) or hash to approve.")
    parser.add_argument(
        "--target",
        "-t",
        default="claude-code",
        help="Target IDE or agent adapter (default: claude-code).",
    )
    parser.add_argument(
        "--ack-stale",
        action="store_true",
        help="Acknowledge repository staleness/drift and record cryptographic acknowledgment.",
    )
    parser.add_argument(
        "--accept-untrusted",
        action="store_true",
        help="Accept and approve an untrusted or externally imported packet.",
    )
    parser.add_argument(
        "--passphrase",
        default=None,
        help="Passphrase for Ed25519 digital signature of approval (swallo[sign]).",
    )
    parser.add_argument("--store", type=Path, default=None, help="Store directory override.")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON.")

    args = parser.parse_args(argv)

    args.target = normalize_target(args.target)
    supported_targets = list_supported_targets()
    if args.target not in supported_targets:
        supported_str = ", ".join(supported_targets)
        raise UsageError(
            f"Unsupported delivery target '{args.target}'. Supported targets: {supported_str}"
        )

    store_dir = (args.store or get_store_dir()).resolve()
    db_path = store_dir / "swallo.db"
    key_path = store_dir / "key"

    if not db_path.exists() or not key_path.exists():
        raise UsageError(f"Store at '{store_dir}' not initialized.")

    conn = get_connection(db_path)
    key_bytes = get_or_create_local_key(key_path)

    # 1. Lookup packet hash
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, hash, project, body, origin FROM packets WHERE id = ? OR hash = ?",
            (args.packet_id, args.packet_id),
        )
        row = cursor.fetchone()
    finally:
        cursor.close()

    if not row:
        raise UsageError(f"Packet '{args.packet_id}' not found in store.")

    pkt_id, pkt_hash, project, body_raw, origin = row[0], row[1], row[2], row[3], row[4]

    # Security check (F8, F21): Imported packets require --accept-untrusted
    if origin == "imported" and not args.accept_untrusted:
        raise UsageError(
            f"Packet '{pkt_id}' was imported from an untrusted vendor export. "
            "Approval requires the --accept-untrusted flag."
        )

    # 2. Terminal Confirmation check (ADR-007, F21)
    # NOTE: --force flag removed (Phase 1-A security fix). The TTY barrier is mandatory.
    # Tests must monkeypatch `swallo.terminal.confirm_on_terminal` or inject stream_in.
    prompt = (
        f"Approve packet '{pkt_id}' (project: '{project}') for delivery to '{args.target}'?"
    )
    confirmed = confirm_on_terminal(prompt, default=False)
    if not confirmed:
        msg = f"Approval aborted by user for packet '{pkt_id}'."
        if args.json:
            print(json.dumps({"status": "aborted", "id": pkt_id, "message": msg}))
        else:
            print(msg, file=sys.stderr)
        return 1

    # 3. Write approval to cryptographic ledger
    mac = approve(conn, key_bytes, pkt_hash, args.target)

    # 4. Optional Ed25519 digital signature
    cfg, _ = load_config(store_dir)
    signing_mode = (
        "passphrase"
        if (args.passphrase is not None or cfg.approve.signing == "passphrase")
        else "off"
    )

    sig_hex: str | None = None
    pub_key_hex: str | None = None

    if signing_mode == "passphrase":
        from swallo.store.signing import (
            StoredSigningMeta,
            derive_key,
            init_signing_keys,
            sign_payload,
            verify_passphrase,
        )

        passphrase = args.passphrase
        if passphrase is None:
            passphrase = getpass.getpass("Enter approval signing passphrase: ")
        if not passphrase:
            raise UsageError("Signing passphrase cannot be empty.")

        meta_file = store_dir / ".signing_meta.json"
        if not meta_file.is_file():
            meta, priv_key = init_signing_keys(passphrase)
            meta.save(meta_file)
        else:
            meta = StoredSigningMeta.load(meta_file)
            if not verify_passphrase(passphrase, meta):
                raise UsageError("Invalid passphrase for approval signing.")
            salt = bytes.fromhex(meta.salt_hex)
            priv_key = derive_key(
                passphrase,
                salt,
                n=meta.scrypt_n,
                r=meta.scrypt_r,
                p=meta.scrypt_p,
            )

        payload = f"approve:{pkt_hash}:{args.target}:{mac}".encode()
        sig_hex = sign_payload(priv_key, payload)
        pub_key_hex = meta.public_key_hex

    # 5. Optional staleness acknowledgment
    ack_mac: str | None = None
    if args.ack_stale:
        repo_root = get_repo_root(Path.cwd()) or Path.cwd().resolve()
        try:
            body_dict = parse_canonical_json(body_raw)
            if isinstance(body_dict, dict):
                packet = Packet.model_validate(body_dict)
                report = check_staleness(packet, repo_root, conn, key_bytes)
                if report.head_commit and report.drift_hash:
                    ack_mac = record_stale_ack(
                        conn,
                        key_bytes,
                        pkt_hash,
                        report.head_commit,
                        report.drift_hash,
                    )
        except Exception:
            ack_mac = None

    result: dict[str, object] = {
        "status": "approved",
        "id": pkt_id,
        "hash": pkt_hash,
        "target": args.target,
        "mac": mac,
    }
    if sig_hex and pub_key_hex:
        result["signature"] = sig_hex
        result["signer_public_key"] = pub_key_hex

    if ack_mac:
        result["ack_mac"] = ack_mac
        result["staleness_acknowledged"] = True

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Packet '{pkt_id}' successfully approved for target '{args.target}'.")
        print(f"  Hash: {pkt_hash}")
        print(f"  MAC:  {mac}")
        if sig_hex:
            print(f"  Signature: {sig_hex}")
            print(f"  Signer Pubkey: {pub_key_hex}")
        if ack_mac:
            print(f"  Staleness Acknowledged (MAC: {ack_mac})")

    return 0
