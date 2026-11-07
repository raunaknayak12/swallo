"""
Gemini Takeout export archive conversation importer.

Per TRD.md section 6.1, CLI_AND_MCP_SPEC.md section 1, and Security.md F8:
- Parses chats.json or conversations.json from Google Takeout Gemini export zip or json.
- Normalizes Gemini prompt/response pairs into canonical message turns.
- Distills code blocks, decisions, and constraints into normalized Swallo packets.
- Ingested packets are stored with origin='imported' and tier T3 provenance.
"""

from __future__ import annotations

import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from swallo.capture.importers.base import BaseImporter, SessionSummary
from swallo.capture.importers.stream import safe_json_loads
from swallo.errors import SecurityError, ValidationError
from swallo.schema.models import Goal, Item, Packet, Provenance, Source

_CODE_BLOCK_PATTERN = re.compile(r"```(?P<lang>[a-zA-Z0-9_\-]+)?\n(?P<code>[\s\S]*?)```")


def _format_timestamp(ts: object) -> str:
    """Format Unix timestamp or ISO string into a standard UTC ISO 8601 string."""
    if ts is None:
        return datetime.now(UTC).isoformat()
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(ts, tz=UTC).isoformat()
        except (ValueError, OverflowError, OSError):
            return datetime.now(UTC).isoformat()
    if isinstance(ts, str):
        return ts
    return datetime.now(UTC).isoformat()


def _extract_text(obj: object) -> str:
    """Extract plain text string from Gemini message or part."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        text = obj.get("text")
        if isinstance(text, str):
            return text
        parts = obj.get("parts")
        if isinstance(parts, list):
            return "\n".join(_extract_text(p) for p in parts if p is not None)
        content = obj.get("content")
        if content is not None:
            return _extract_text(content)
    if isinstance(obj, list):
        return "\n".join(_extract_text(item) for item in obj if item is not None)
    return str(obj or "")


class GeminiTakeoutImporter(BaseImporter):
    """Importer for Google Takeout Gemini exports (chats.json or archive)."""

    name = "gemini"

    def _load_raw_data(self, archive_path: Path) -> list[dict[str, object]]:
        """Load and parse chats list from zip archive or raw json file."""
        path = self.guard.validate_archive_path(archive_path)

        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path, "r") as zf:
                self.guard.verify_zip_structure(zf)
                # Find chats.json, conversations.json, or any candidate json
                target_member = None
                for member in zf.namelist():
                    name_lower = member.lower()
                    if name_lower.endswith("chats.json") or name_lower.endswith(
                        "conversations.json"
                    ):
                        target_member = member
                        break
                if not target_member:
                    for member in zf.namelist():
                        if member.endswith(".json") and not member.startswith("__MACOSX"):
                            target_member = member
                            break

                if not target_member:
                    raise ValidationError(
                        f"Archive '{archive_path.name}' does not contain 'chats.json'."
                    )
                raw_bytes = self.guard.safe_read_member(zf, target_member)
                parsed = safe_json_loads(raw_bytes, max_depth=self.settings.max_json_depth)
        else:
            raw_text = path.read_text(encoding="utf-8")
            parsed = safe_json_loads(raw_text, max_depth=self.settings.max_json_depth)

        if isinstance(parsed, dict):
            # Check for wrapped structure like {"chats": [...]} or {"conversations": [...]}
            for wrapper_key in ("chats", "conversations", "sessions"):
                wrapped = parsed.get(wrapper_key)
                if isinstance(wrapped, list):
                    res: list[dict[str, object]] = []
                    for item in wrapped:
                        if isinstance(item, dict):
                            res.append(item)
                    return res
            return [parsed]

        if isinstance(parsed, list):
            res_list: list[dict[str, object]] = []
            for item in parsed:
                if isinstance(item, dict):
                    res_list.append(item)
            return res_list

        raise ValidationError(
            f"Expected JSON object or array of chats in '{archive_path.name}', got {type(parsed)}."
        )

    def list_sessions(self, archive_path: Path) -> list[SessionSummary]:
        """List all conversation sessions available in the Gemini archive."""
        conversations = self._load_raw_data(archive_path)
        summaries: list[SessionSummary] = []

        for idx, conv in enumerate(conversations):
            conv_id = str(conv.get("id") or conv.get("chat_id") or f"gemini-chat-{idx + 1}")
            title = str(conv.get("title") or "Untitled Conversation")
            create_ts = _format_timestamp(
                conv.get("startTime") or conv.get("created_at") or conv.get("create_time")
            )
            update_ts = _format_timestamp(
                conv.get("endTime") or conv.get("updated_at") or conv.get("update_time")
            )

            # Count messages
            messages = conv.get("messages") or conv.get("history") or conv.get("chat_messages")
            msg_count = len(messages) if isinstance(messages, list) else 0

            summaries.append(
                SessionSummary(
                    id=conv_id,
                    title=title,
                    message_count=msg_count,
                    created_at=create_ts,
                    updated_at=update_ts,
                )
            )

        return summaries

    def extract_session(
        self,
        archive_path: Path,
        session_id: str,
        project: str = "default",
    ) -> Packet:
        """Extract a single conversation session and transform it into a Packet."""
        conversations = self._load_raw_data(archive_path)
        matching: dict[str, object] | None = None

        for idx, conv in enumerate(conversations):
            cid = str(conv.get("id") or conv.get("chat_id") or f"gemini-chat-{idx + 1}")
            if cid == session_id:
                matching = conv
                break

        if not matching:
            raise ValidationError(
                f"Session ID '{session_id}' not found in '{archive_path.name}'."
            )

        title = str(matching.get("title") or "Untitled Conversation")
        create_ts = _format_timestamp(
            matching.get("startTime")
            or matching.get("created_at")
            or matching.get("create_time")
        )

        messages = (
            matching.get("messages")
            or matching.get("history")
            or matching.get("chat_messages")
        )
        ordered_messages: list[tuple[str, str]] = []  # (role, text)

        if isinstance(messages, list):
            for msg in messages:
                if isinstance(msg, dict):
                    author = str(
                        msg.get("author") or msg.get("role") or msg.get("sender") or "USER"
                    ).upper()
                    role = "user" if author in ("USER", "HUMAN") else "assistant"
                    text = _extract_text(msg).strip()
                    if text:
                        ordered_messages.append((role, text))

        items: list[Item] = []
        user_prompts: list[str] = []

        for role, text in ordered_messages:
            if role == "user":
                user_prompts.append(text)
                continue

            # Extract code blocks from assistant replies
            for match in _CODE_BLOCK_PATTERN.finditer(text):
                lang = (match.group("lang") or "code").strip()
                code_content = match.group("code").strip()
                if len(code_content) > 10:
                    items.append(
                        Item(
                            kind="decision",
                            text=f"```{lang}\n{code_content}\n```",
                            topic=lang,
                            provenance=[Provenance(session_id=session_id)],
                        )
                    )

            # Extract lines that look like decisions
            for line in text.splitlines():
                stripped = line.strip()
                if any(
                    stripped.lower().startswith(prefix)
                    for prefix in ("we will", "we should", "decision:", "decided:", "- [x]")
                ):
                    items.append(
                        Item(
                            kind="decision",
                            text=stripped,
                            topic="decision",
                            provenance=[Provenance(session_id=session_id)],
                        )
                    )

        # Fallback if no specific decision lines found: extract general summary lines
        if not items and ordered_messages:
            for role, text in ordered_messages:
                if role == "assistant" and len(text) > 20:
                    first_para = text.split("\n\n")[0].strip()
                    items.append(
                        Item(
                            kind="decision",
                            text=first_para[:500],
                            topic="chat_summary",
                            provenance=[Provenance(session_id=session_id)],
                        )
                    )
                    break

        goal_text = title
        if user_prompts and (title == "Untitled Conversation" or len(title) < 5):
            goal_text = user_prompts[0][:200].replace("\n", " ").strip()

        source = Source(
            session_id=session_id,
            agent="gemini",
            capture_method="export",
            captured_at=create_ts,
        )

        return Packet(
            schema_version="0.1",
            project=project,
            created_at=create_ts,
            goal=Goal(text=goal_text),
            items=items,
            sources=[source],
        )

    def extract_all(
        self,
        archive_path: Path,
        project: str = "default",
    ) -> list[Packet]:
        """Extract all conversation sessions from the archive as Packets."""
        sessions = self.list_sessions(archive_path)
        packets: list[Packet] = []
        for s in sessions:
            try:
                pkt = self.extract_session(archive_path, s.id, project=project)
                packets.append(pkt)
            except (ValidationError, SecurityError, KeyError, ValueError):
                continue
        return packets
