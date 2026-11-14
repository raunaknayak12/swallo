"""Tests for swallo load command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from swallo.cli import main
from swallo.store.db import get_connection


@pytest.fixture
def sample_packet() -> dict[str, object]:
    return {
        "schema_version": "0.1",
        "project": "TestApp",
        "created_at": "2026-11-04T00:00:00Z",
        "sources": [
            {
                "session_id": "s_load",
                "agent": "user",
                "capture_method": "manual",
                "captured_at": "2026-11-04T00:00:00Z",
            }
        ],
        "goal": {"text": "Refactor token bucket for rate limiter"},
        "items": [
            {
                "kind": "decision",
                "text": "Set refill rate to 10 tokens per second.",
                "critical": True,
            },
            {
                "kind": "constraint",
                "text": "Bucket maximum capacity is 100 tokens.",
                "critical": False,
            },
        ],
    }


def test_load_command_lifecycle(
    tmp_path: Path, sample_packet: dict[str, object], capsys: pytest.CaptureFixture[str]
) -> None:
    store_dir = tmp_path / "load_store"

    # 1. Initialize store
    assert main(["init", "--store", str(store_dir), "--project", "TestApp", "--json"]) == 0
    capsys.readouterr()

    # 2. Save packet
    pkt_file = tmp_path / "packet.json"
    pkt_file.write_text(json.dumps(sample_packet), encoding="utf-8")
    assert main(["save", str(pkt_file), "--store", str(store_dir)]) == 0
    capsys.readouterr()

    conn = get_connection(store_dir / "swallo.db")
    cur = conn.cursor()
    cur.execute("SELECT id FROM packets LIMIT 1")
    row = cur.fetchone()
    assert row is not None
    pkt_id = str(row[0])
    conn.close()

    # 3. Load before approval -> exit code 6
    fail_code = main(["load", pkt_id, "--to", "chat", "--store", str(store_dir)])
    assert fail_code == 6
    capsys.readouterr()

    # 4. Approve for chat
    with patch("swallo.commands.approve.confirm_on_terminal", return_value=True):
        assert main(["approve", pkt_id, "--target", "chat", "--store", str(store_dir)]) == 0
    capsys.readouterr()

    # 5. Load to chat without --copied
    load_code = main(["load", pkt_id, "--to", "chat", "--store", str(store_dir)])
    assert load_code == 0
    captured = capsys.readouterr()
    assert "===SWALLO_FENCE_" in captured.out
    assert "Refactor token bucket for rate limiter" in captured.out
    assert "Set refill rate to 10 tokens per second." in captured.out

    # 6. Load with --copied -> verify audit event recorded
    load_copied_code = main([
        "load",
        pkt_id,
        "--to",
        "chat",
        "--copied",
        "--store",
        str(store_dir),
    ])
    assert load_copied_code == 0
    capsys.readouterr()

    conn = get_connection(store_dir / "swallo.db")
    cur = conn.cursor()
    cur.execute("SELECT type, target FROM events WHERE type = 'copied'")
    event_row = cur.fetchone()
    assert event_row is not None
    assert event_row[0] == "copied"
    assert event_row[1] == "chat"
    conn.close()

    # 7. Load with --json
    json_code = main(["load", pkt_id, "--to", "chat", "--json", "--store", str(store_dir)])
    assert json_code == 0
    captured_json = capsys.readouterr()
    parsed_json = json.loads(captured_json.out)
    assert parsed_json["status"] == "loaded"
    assert parsed_json["packet_id"] == pkt_id
    assert "===SWALLO_FENCE_" in parsed_json["content"]
