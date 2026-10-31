"""
Pydantic models for swallo context packet schema v0.1.

Per PACKET_SCHEMA.md, DECISIONS.md (ADR-001, ADR-003, ADR-004, ADR-024, ADR-025).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from swallo.errors import ValidationError
from swallo.schema.canonical import derive_item_id, derive_packet_id, packet_hash
from swallo.schema.limits import (
    CURRENT_SCHEMA_VERSION,
    MAX_ITEM_TEXT_LEN,
    MAX_ITEMS_PER_KIND,
    MAX_PACKET_BYTES,
    SUPPORTED_SCHEMA_VERSIONS,
)

# Reject ASCII control chars (0x00-0x1F, 0x7F) except newline, carriage return, tab
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sanitize_text(text: str) -> str:
    """Validate and normalize text: NFC normalization and check control characters."""
    if _CONTROL_CHAR_RE.search(text):
        raise ValidationError("Text contains prohibited control characters")
    return unicodedata.normalize("NFC", text)


class Transcript(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object: str = Field(description="Content-addressed object hash, e.g. sha256:...")
    redacted: bool = Field(default=True, description="Whether transcript is redacted")


class Source(BaseModel):
    model_config = ConfigDict(extra="ignore")  # Ignore in-file trust claims per ADR-004

    session_id: str
    agent: str
    capture_method: Literal["export", "paste", "connector", "ide-agent", "manual"]
    captured_at: str
    transcript: Transcript | None = None

    @field_validator("agent", "session_id", mode="before")
    @classmethod
    def _validate_str(cls, v: object) -> str:
        if not isinstance(v, str):
            raise ValidationError(f"Expected string, got {type(v).__name__}")
        return _sanitize_text(v)


class Goal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str

    @field_validator("text", mode="before")
    @classmethod
    def _validate_text(cls, v: object) -> str:
        if not isinstance(v, str):
            raise ValidationError(f"Expected string, got {type(v).__name__}")
        return _sanitize_text(v)


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    span: list[int] | tuple[int, int] | None = None

    @field_validator("span")
    @classmethod
    def _validate_span(cls, v: list[int] | tuple[int, int] | None) -> list[int] | None:
        if v is None:
            return None
        if len(v) != 2:
            raise ValidationError("Span must contain exactly 2 integer offsets [start, end]")
        if v[0] < 0 or v[1] < v[0]:
            raise ValidationError("Invalid span offsets")
        return list(v)


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    kind: Literal["decision", "constraint", "question", "artifact_ref"]
    text: str
    topic: str | None = None
    value: str | None = None
    critical: bool = False
    provenance: list[Provenance] = Field(default_factory=list)

    @field_validator("text", mode="before")
    @classmethod
    def _validate_item_text(cls, v: object) -> str:
        if not isinstance(v, str):
            raise ValidationError(f"Expected string, got {type(v).__name__}")
        if len(v) > MAX_ITEM_TEXT_LEN:
            msg = f"Item text exceeds maximum length of {MAX_ITEM_TEXT_LEN} characters"
            raise ValidationError(msg)
        return _sanitize_text(v)

    @field_validator("topic", "value", mode="before")
    @classmethod
    def _validate_optional_str(cls, v: object) -> str | None:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValidationError(f"Expected string, got {type(v).__name__}")
        return _sanitize_text(v)


class Conflict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    items: list[str]
    reason: Literal["same_topic_different_value", "override_language", "heuristic_negation"]
    status: Literal["unresolved", "resolved"] = "unresolved"
    resolution: str | None = None


class RepoState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    git_commit: str
    dirty: bool = False
    files: dict[str, str] = Field(default_factory=dict)

    @field_validator("files")
    @classmethod
    def _validate_file_paths(cls, files: dict[str, str]) -> dict[str, str]:
        for path in files:
            if path.startswith(("/", "\\")) or ".." in path.split("/"):
                raise ValidationError(f"File paths must be repo-relative: {path!r}")
        return files


class Redaction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = 0
    types: list[str] = Field(default_factory=list)


class Packet(BaseModel):
    model_config = ConfigDict(extra="ignore")  # Ignore unknown/trust fields on load (ADR-004)

    schema_version: str = CURRENT_SCHEMA_VERSION
    id: str | None = None
    created_at: str
    project: str
    parent: str | None = None
    merged_from: list[str] = Field(default_factory=list)
    sources: list[Source]
    goal: Goal
    items: list[Item] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    repo_state: RepoState | None = None
    redaction: Redaction | None = None

    @field_validator("schema_version")
    @classmethod
    def _validate_version(cls, v: str) -> str:
        if v not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValidationError(
                f"Unsupported schema_version: {v!r}. Supported: {SUPPORTED_SCHEMA_VERSIONS}"
            )
        return v

    @model_validator(mode="after")
    def _validate_packet_limits(self) -> Packet:
        # Check items per kind
        kind_counts: dict[str, int] = {}
        for item in self.items:
            kind_counts[item.kind] = kind_counts.get(item.kind, 0) + 1
            if kind_counts[item.kind] > MAX_ITEMS_PER_KIND:
                msg = f"Exceeded maximum items for kind '{item.kind}' ({MAX_ITEMS_PER_KIND})"
                raise ValidationError(msg)

        # Assign derived IDs per ADR-025 if missing or recompute
        self.derive_ids()

        # Check total serialized packet byte size
        raw_json = self.model_dump_json()
        if len(raw_json.encode("utf-8")) > MAX_PACKET_BYTES:
            raise ValidationError(f"Packet exceeds maximum size of {MAX_PACKET_BYTES} bytes")

        return self

    def derive_ids(self) -> None:
        """Derive packet ID and item IDs deterministically per ADR-025."""
        # Derive item IDs first
        taken_item_ids: set[str] = set()
        for item in self.items:
            item_id = derive_item_id(item.kind, item.text, taken=taken_item_ids)
            item.id = item_id
            taken_item_ids.add(item_id)

        # Derive packet ID from packet hash
        pkt_dict = self.model_dump(mode="json")
        p_hash = packet_hash(pkt_dict)
        self.id = derive_packet_id(p_hash)
