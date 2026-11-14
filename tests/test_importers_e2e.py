"""
End-to-end integration tests for vendor conversation importers.

Covers:
- ChatGPT export (.zip and .json).
- Claude export (.zip and .json).
- Gemini Takeout export (.zip and .json).
- CLI commands: 'swallo prompt' and 'swallo import'.
- Cryptographic ledger approval gate requiring --accept-untrusted for imported packets.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from swallo.capture.importers.chatgpt import ChatGPTImporter
from swallo.capture.importers.claude_export import ClaudeImporter
from swallo.capture.importers.gemini_takeout import GeminiTakeoutImporter
from swallo.cli import main
from swallo.config import ImporterSettings
from swallo.errors import UsageError
from swallo.store.db import get_connection


def _create_zip(filename: str, content: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(filename, content)
    return buf.getvalue()


@pytest.fixture
def chatgpt_zip_path(tmp_path: Path) -> Path:
    conversations = [
        {
            "id": "conv-chatgpt-1",
            "title": "Build Architecture",
            "create_time": 1700000000.0,
            "update_time": 1700001000.0,
            "mapping": {
                "node-1": {
                    "message": {
                        "create_time": 1700000100.0,
                        "author": {"role": "user"},
                        "content": {"parts": ["How should we design the database?"]},
                    }
                },
                "node-2": {
                    "message": {
                        "create_time": 1700000200.0,
                        "author": {"role": "assistant"},
                        "content": {
                            "parts": [
                                "We will use SQLite with WAL mode.\n"
                                "```sql\nCREATE TABLE items;\n```"
                            ]
                        },
                    }
                },
            },
        }
    ]
    raw = json.dumps(conversations).encode("utf-8")
    p = tmp_path / "chatgpt_export.zip"
    p.write_bytes(_create_zip("conversations.json", raw))
    return p


@pytest.fixture
def claude_zip_path(tmp_path: Path) -> Path:
    conversations = [
        {
            "uuid": "conv-claude-1",
            "name": "Refactor Modules",
            "created_at": "2024-01-15T10:00:00Z",
            "updated_at": "2024-01-15T11:00:00Z",
            "chat_messages": [
                {
                    "sender": "human",
                    "text": "Please refactor the crypto layer.",
                },
                {
                    "sender": "assistant",
                    "text": (
                        "Decision: we will replace md5 with sha256.\n"
                        "```python\nimport hashlib\nhashlib.sha256()\n```"
                    ),
                },
            ],
        }
    ]
    raw = json.dumps(conversations).encode("utf-8")
    p = tmp_path / "claude_export.zip"
    p.write_bytes(_create_zip("conversations.json", raw))
    return p


@pytest.fixture
def gemini_json_path(tmp_path: Path) -> Path:
    chats = {
        "chats": [
            {
                "id": "gemini-chat-1",
                "title": "API Gateway Design",
                "startTime": "2024-02-01T08:00:00Z",
                "endTime": "2024-02-01T09:00:00Z",
                "messages": [
                    {"author": "USER", "text": "What API protocol should we use?"},
                    {
                        "author": "GEMINI",
                        "text": (
                            "We should implement JSON-RPC 2.0 over standard IO.\n"
                            "```json\n{\"jsonrpc\": \"2.0\"}\n```"
                        ),
                    },
                ],
            }
        ]
    }
    p = tmp_path / "gemini_chats.json"
    p.write_text(json.dumps(chats), encoding="utf-8")
    return p


def test_chatgpt_importer_direct(chatgpt_zip_path: Path) -> None:
    importer = ChatGPTImporter(ImporterSettings())
    sessions = importer.list_sessions(chatgpt_zip_path)
    assert len(sessions) == 1
    assert sessions[0].id == "conv-chatgpt-1"
    assert sessions[0].title == "Build Architecture"
    assert sessions[0].message_count == 2

    packet = importer.extract_session(chatgpt_zip_path, "conv-chatgpt-1", project="myproj")
    assert packet.project == "myproj"
    assert packet.goal.text == "Build Architecture"
    assert len(packet.items) >= 2
    assert any("CREATE TABLE" in item.text for item in packet.items)
    assert any("We will use SQLite" in item.text for item in packet.items)


def test_claude_importer_direct(claude_zip_path: Path) -> None:
    importer = ClaudeImporter(ImporterSettings())
    sessions = importer.list_sessions(claude_zip_path)
    assert len(sessions) == 1
    assert sessions[0].id == "conv-claude-1"
    assert sessions[0].title == "Refactor Modules"

    packet = importer.extract_session(claude_zip_path, "conv-claude-1", project="claude-proj")
    assert packet.project == "claude-proj"
    assert len(packet.items) >= 2
    assert any("hashlib.sha256" in item.text for item in packet.items)


def test_gemini_importer_direct(gemini_json_path: Path) -> None:
    importer = GeminiTakeoutImporter(ImporterSettings())
    sessions = importer.list_sessions(gemini_json_path)
    assert len(sessions) == 1
    assert sessions[0].id == "gemini-chat-1"
    assert sessions[0].title == "API Gateway Design"

    packet = importer.extract_session(gemini_json_path, "gemini-chat-1", project="gemini-proj")
    assert packet.project == "gemini-proj"
    assert any("JSON-RPC 2.0" in item.text for item in packet.items)


def test_cli_prompt_command(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["prompt", "--target", "claude-code", "--project", "test-sys"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Claude Code IDE agent" in out
    assert '"project": "test-sys"' in out


def test_cli_import_and_approval_gate(
    tmp_path: Path,
    chatgpt_zip_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store_dir = tmp_path / "store"

    # Initialize store
    init_rc = main(["init", "--store", str(store_dir), "--project", "audit-proj"])
    assert init_rc == 0
    capsys.readouterr()

    # List sessions via CLI
    list_rc = main([
        "import",
        "chatgpt",
        str(chatgpt_zip_path),
        "--list-sessions",
        "--store",
        str(store_dir),
    ])
    assert list_rc == 0
    list_out = capsys.readouterr().out
    assert "conv-chatgpt-1" in list_out

    # Import session via CLI
    import_rc = main([
        "import",
        "chatgpt",
        str(chatgpt_zip_path),
        "--session",
        "conv-chatgpt-1",
        "--store",
        str(store_dir),
        "--project",
        "audit-proj",
        "--json",
    ])
    assert import_rc == 0
    import_raw = capsys.readouterr().out
    import_json = json.JSONDecoder().decode(import_raw)
    assert isinstance(import_json, list)
    assert len(import_json) == 1
    pkt_id = import_json[0]["id"]
    assert pkt_id.startswith("pkt_")

    # Verify origin in SQLite is 'imported'
    db_path = store_dir / "swallo.db"
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT origin FROM packets WHERE id = ?", (pkt_id,))
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == "imported"
    cursor.close()
    conn.close()

    # Attempt to approve without --accept-untrusted (must raise UsageError)
    with pytest.raises(UsageError, match="--accept-untrusted"):
        with patch("swallo.commands.approve.confirm_on_terminal", return_value=True):
            main([
                "approve",
                pkt_id,
                "--store",
                str(store_dir),
                "--target",
                "chat",
            ])

    # Approve with --accept-untrusted (must succeed)
    with patch("swallo.commands.approve.confirm_on_terminal", return_value=True):
        approve_rc = main([
            "approve",
            pkt_id,
            "--store",
            str(store_dir),
            "--target",
            "chat",
            "--accept-untrusted",
        ])
    assert approve_rc == 0
    approve_out = capsys.readouterr().out
    assert "successfully approved" in approve_out
