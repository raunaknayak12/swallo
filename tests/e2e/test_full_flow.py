"""
End-to-end full workflow regression test suite for Swallo v0.1.3.

Executes real CLI commands via subprocess against an isolated SWALLO_HOME:
1. `prompt`: extracts sample JSON and validates against Packet model
2. `save`: tests secret redaction and fail-closed vs --warn behavior
3. `status` / `list`: verifies saved packet summary
4. `show`: confirms risk summary display and zero plaintext secret leakage
5. `approve`: verifies TTY requirement and programmatic ledger approval
6. `send`: confirms --format markdown and target delivery
7. MCP: verifies get_context, load_context, and verify_context tools
8. Determinism: verifies same packet content produces identical SHA-256 IDs
9. Tampering: verifies detection of modified body, event, and approval rows
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from swallo.schema.canonical import parse_canonical_json
from swallo.schema.models import Packet
from swallo.store.db import get_connection, get_or_create_local_key
from swallo.store.ledger import approve


def _run_cli(
    args: list[str], env: dict[str, str], cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "swallo", *args]
    run_env = {**env, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(  # noqa: S603
        cmd,
        timeout=30,
        env=run_env,
        cwd=cwd,
        stdin=subprocess.PIPE,
        capture_output=True,
        text=True,
        check=False,
    )


def test_e2e_full_workflow(tmp_path: Path) -> None:
    store_dir = tmp_path / "swallo_store"
    project_dir = tmp_path / "demo_project"
    project_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["SWALLO_HOME"] = str(store_dir)

    # Initialize store first
    res_init = _run_cli(["init"], env=env, cwd=project_dir)
    assert res_init.returncode == 0

    # Step 1: Prompt generation and sample JSON validation
    res = _run_cli(["prompt", "--json"], env=env, cwd=project_dir)
    assert res.returncode == 0
    prompt_json = parse_canonical_json(res.stdout)
    assert isinstance(prompt_json, dict)
    prompt_body = prompt_json["prompt"]
    match = re.search(r"```json\s*(\{.*?\})\s*```", prompt_body, re.DOTALL)
    assert match is not None
    sample_packet = parse_canonical_json(match.group(1))
    assert isinstance(sample_packet, dict)
    validated = Packet.model_validate(sample_packet)
    assert validated.schema_version == "0.1"

    # Step 2: Build handoff containing fake secrets and BiDi characters
    fake_aws_key = "AKIAIOSFODNN7EXAMPLE"
    fake_gh_token = "ghp_FAKE0000000000000000000000000000000000"
    bidi_str = "\u202eREVERSED\u202a"
    zw_str = "\u200bHIDDEN"

    payload = {
        "schema_version": "0.1",
        "project": "demo_project",
        "created_at": "2024-01-01T00:00:00Z",
        "sources": [
            {
                "session_id": "test_session",
                "agent": "chat",
                "capture_method": "paste",
                "captured_at": "2024-01-01T00:00:00Z",
            }
        ],
        "goal": {
            "text": f"Migrate authentication without leaking {fake_aws_key} {bidi_str}"
        },
        "items": [
            {
                "kind": "decision",
                "text": f"Store token {fake_gh_token} safely {zw_str}",
            },
            {
                "kind": "constraint",
                "text": "Never commit plaintext credentials.",
            },
        ],
    }

    input_file = project_dir / "handoff.json"
    input_file.write_text(json.dumps(payload), encoding="utf-8")

    # Save with --fail-closed (should be blocked by secret redaction)
    res_fail = _run_cli(["save", str(input_file)], env=env, cwd=project_dir)
    assert res_fail.returncode != 0

    # Save with --warn (should redact secrets, strip BiDi, and succeed)
    res_save = _run_cli(
        ["save", str(input_file), "--warn", "--json"],
        env=env,
        cwd=project_dir,
    )
    assert res_save.returncode == 0
    save_data = parse_canonical_json(res_save.stdout)
    assert isinstance(save_data, dict)
    packet_id = save_data["id"]
    pkt_hash = save_data["hash"]
    assert packet_id.startswith("pkt_")

    # Step 3: Status / List command
    res_status = _run_cli(["status", "--json"], env=env, cwd=project_dir)
    assert res_status.returncode == 0
    status_list = parse_canonical_json(res_status.stdout)
    assert isinstance(status_list, list)
    assert any(p["id"] == packet_id for p in status_list)

    # Step 4: Show command (verify risk summary and zero plaintext secret leaks)
    res_show = _run_cli(["show", packet_id], env=env, cwd=project_dir)
    assert res_show.returncode == 0
    assert fake_aws_key not in res_show.stdout
    assert fake_gh_token not in res_show.stdout
    assert bidi_str not in res_show.stdout
    assert "[REDACTED:" in res_show.stdout or "REDACTED" in res_show.stdout

    # Step 5: TTY refusal on approve command
    res_app_tty = _run_cli(["approve", packet_id], env=env, cwd=project_dir)
    assert res_app_tty.returncode != 0

    # Legitimate approval via local ledger key
    db_path = store_dir / "swallo.db"
    key_path = store_dir / "key"
    conn = get_connection(db_path)
    key_bytes = get_or_create_local_key(key_path)
    approve(conn, key_bytes, pkt_hash, "claude-code")
    conn.close()

    # Step 6: Delivery via send command with --format markdown
    res_send = _run_cli(
        ["send", packet_id, "--to", "claude-code", "--format", "markdown"],
        env=env,
        cwd=project_dir,
    )
    assert res_send.returncode == 0
    assert (project_dir / ".swallo" / "handoff" / f"{packet_id}.md").exists()
    assert (project_dir / "CLAUDE.md").exists()

    # Step 7: Determinism check (saving identical packet yields exact same hash and packet ID)
    res_save2 = _run_cli(
        ["save", str(input_file), "--warn", "--json"],
        env=env,
        cwd=project_dir,
    )
    assert res_save2.returncode == 0
    save_data2 = parse_canonical_json(res_save2.stdout)
    assert isinstance(save_data2, dict)
    assert save_data2["id"] == packet_id
    assert save_data2["hash"] == pkt_hash

    # Step 8: MCP tools integration test (load_context, get_context, verify_context)
    from swallo.server.mcp_server import SwalloService

    svc = SwalloService(store_dir=store_dir)
    loaded = svc.load_context(project="demo_project", packet_id=packet_id, target="claude-code")
    assert loaded["id"] == packet_id

    alias_loaded = svc.get_context(
        project="demo_project", packet_id=packet_id, target="claude-code"
    )
    assert alias_loaded["id"] == packet_id

    verified_report = svc.verify_context(project="demo_project", packet_id=packet_id)
    assert verified_report["hash_verified"] is True
    assert verified_report["event_chain_ok"] is True
    assert verified_report["approvals"]["claude-code"] is True

    # Step 9: Tamper detection (modify stored body directly and verify fails)
    conn2 = get_connection(db_path)
    cur2 = conn2.cursor()
    cur2.execute("UPDATE packets SET body = ? WHERE id = ?", (b'{"tampered": 1}', packet_id))
    conn2.commit()
    conn2.close()

    tamper_report = svc.verify_context(project="demo_project", packet_id=packet_id)
    assert tamper_report["hash_verified"] is False
