"""
ChatGPT export archive conversation importer.

Per TRD.md section 6.1, CLI_AND_MCP_SPEC.md section 1, and Security.md F8:
- Parses conversations.json from ChatGPT data export zip or standalone json files.
- Extracts chronological message turns from the conversation tree mapping.
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


def _extract_message_text(content_obj: object) -> str:
    """Extract plain text string from ChatGPT content payload."""
    if not isinstance(content_obj, dict):
        return str(content_obj or "")
    parts = content_obj.get("parts")
    if isinstance(parts, list):
        return "\n".join(str(p) for p in parts if p is not None)
    text = content_obj.get("text")
    if text is not None:
        return str(text)
    return ""


class ChatGPTImporter(BaseImporter):
    """Importer for ChatGPT export archives and conversations.json."""

    name = "chatgpt"

    def _load_raw_data(self, archive_path: Path) -> list[dict[str, object]]:
        """Load and parse conversations list from zip archive or raw json file."""
        path = self.guard.validate_archive_path(archive_path)

        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path, "r") as zf:
                self.guard.verify_zip_structure(zf)
                # Find conversations.json
                target_member = None
                for member in zf.namelist():
                    if member == "conversations.json" or member.endswith("/conversations.json"):
                        target_member = member
                        break
                if not target_member:
                    raise ValidationError(
                        f"Archive '{archive_path.name}' does not contain 'conversations.json'."
                    )
                raw_bytes = self.guard.safe_read_member(zf, target_member)
                parsed = safe_json_loads(raw_bytes, max_depth=self.settings.max_json_depth)
        else:
            raw_text = path.read_text(encoding="utf-8")
            parsed = safe_json_loads(raw_text, max_depth=self.settings.max_json_depth)

        if isinstance(parsed, list):
            res: list[dict[str, object]] = []
            for item in parsed:
                if isinstance(item, dict):
                    res.append(item)
            return res
        if isinstance(parsed, dict):
            # Single conversation export
            return [parsed]
        raise ValidationError(
            f"Expected JSON array of conversations in '{archive_path.name}', got {type(parsed)}."
        )

    def list_sessions(self, archive_path: Path) -> list[SessionSummary]:
        """List all conversation sessions available in the ChatGPT archive."""
        conversations = self._load_raw_data(archive_path)
        summaries: list[SessionSummary] = []

        for conv in conversations:
            conv_id = str(conv.get("id") or "")
            title = str(conv.get("title") or "Untitled Conversation")
            create_ts = _format_timestamp(conv.get("create_time"))
            update_ts = _format_timestamp(conv.get("update_time"))

            # Count message nodes
            mapping = conv.get("mapping")
            msg_count = 0
            if isinstance(mapping, dict):
                for node in mapping.values():
                    if isinstance(node, dict) and node.get("message") is not None:
                        msg_count += 1

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
        matching = None
        for conv in conversations:
            if str(conv.get("id")) == session_id:
                matching = conv
                break

        if not matching:
            raise ValidationError(
                f"Session ID '{session_id}' not found in '{archive_path.name}'."
            )

        title = str(matching.get("title") or "Untitled Conversation")
        create_ts = _format_timestamp(matching.get("create_time"))
        mapping = matching.get("mapping")

        # Collect ordered messages
        ordered_messages: list[tuple[str, str]] = []  # (role, text)
        if isinstance(mapping, dict):
            nodes = [n for n in mapping.values() if isinstance(n, dict) and n.get("message")]

            def _sort_key(node: dict[str, object]) -> float:
                msg = node.get("message")
                if isinstance(msg, dict):
                    t = msg.get("create_time")
                    if isinstance(t, (int, float)):
                        return float(t)
                return 0.0

            nodes.sort(key=_sort_key)

            for n in nodes:
                msg = n.get("message")
                if isinstance(msg, dict):
                    author = msg.get("author")
                    role = "user"
                    if isinstance(author, dict):
                        role = str(author.get("role") or "user")
                    text = _extract_message_text(msg.get("content")).strip()
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
            agent="chatgpt",
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
