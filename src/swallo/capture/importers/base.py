"""
Base importer interfaces and archive security guards for vendor export ingestion.

Per TRD.md sections 6.1 and 10, CLI_AND_MCP_SPEC.md section 1, and Security.md F8:
- Defends against Zip-Slip path traversal attacks (nested .., absolute paths, drive letters).
- Defends against zip decompression bombs via chunked reading, ratio and size caps.
- Caps maximum archive size, entry count, and cumulative uncompressed bytes.
- Disallows archive member names from ever being used directly as filesystem paths.
"""

from __future__ import annotations

import re
import stat
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from swallo.config import ImporterSettings
from swallo.errors import SecurityError, ValidationError
from swallo.schema.models import Packet

_DRIVE_LETTER_PATTERN = re.compile(r"^[a-zA-Z]:")
_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class SessionSummary:
    """Metadata summary of a conversation session extracted from an archive."""

    id: str
    title: str
    message_count: int
    created_at: str
    updated_at: str | None = None


class ArchiveGuard:
    """
    Security guardrails for reading untrusted archive files.
    Enforces size, ratio, entry count, and path traversal checks (F8).
    """

    def __init__(self, settings: ImporterSettings | None = None) -> None:
        self.settings = settings or ImporterSettings()

    def validate_archive_path(self, path: Path | str) -> Path:
        """Validate that archive path exists and does not exceed maximum archive size."""
        resolved = Path(path).resolve()
        if not resolved.is_file():
            raise ValidationError(f"Archive file does not exist: {resolved}")

        size = resolved.stat().st_size
        if size > self.settings.max_archive_bytes:
            raise SecurityError(
                f"Archive size ({size} bytes) exceeds maximum permitted limit "
                f"({self.settings.max_archive_bytes} bytes)."
            )
        return resolved

    @staticmethod
    def is_safe_member_name(name: str) -> bool:
        """
        Check if an archive entry name is safe against path traversal (Zip-Slip).
        Rejects .., leading slashes, Windows drive letters, null bytes, and control characters.
        """
        if not name or _CONTROL_CHAR_PATTERN.search(name):
            return False

        # Reject Windows drive letters (e.g. C:file)
        if _DRIVE_LETTER_PATTERN.match(name):
            return False

        # Normalize separators
        normalized = name.replace("\\", "/")

        # Reject absolute paths (POSIX / or Windows \ or double slash //)
        if normalized.startswith("/") or normalized.startswith("//"):
            return False

        # Reject path traversal components
        parts = normalized.split("/")
        return not any(part == ".." for part in parts)

    def verify_zip_structure(self, zf: zipfile.ZipFile) -> None:
        """
        Verify that a ZipFile does not violate entry count or path traversal limits.
        """
        infolist = zf.infolist()
        if len(infolist) > self.settings.max_entries:
            raise SecurityError(
                f"Archive contains {len(infolist)} entries, exceeding maximum permitted "
                f"entry count ({self.settings.max_entries})."
            )

        for info in infolist:
            if not self.is_safe_member_name(info.filename):
                raise SecurityError(
                    f"Path traversal detected in archive entry: '{info.filename}'."
                )

            # Check if entry is a symlink
            mode = info.external_attr >> 16
            if mode != 0 and stat.S_ISLNK(mode):
                raise SecurityError(
                    f"Symlinks are disallowed in archive entries: '{info.filename}'."
                )

    def safe_read_member(self, zf: zipfile.ZipFile, member_name: str) -> bytes:
        """
        Safely decompress and read an archive member with decompression bomb defenses.
        Monitors cumulative uncompressed bytes and compression ratio in 64 KB chunks.
        """
        if not self.is_safe_member_name(member_name):
            raise SecurityError(f"Unsafe member name: '{member_name}'.")

        try:
            info = zf.getinfo(member_name)
        except KeyError as err:
            raise ValidationError(f"Member '{member_name}' not found in archive.") from err

        # Check declared uncompressed size against maximum limit
        if info.file_size > self.settings.max_uncompressed_bytes:
            raise SecurityError(
                f"Member '{member_name}' uncompressed size ({info.file_size} bytes) "
                f"exceeds maximum limit ({self.settings.max_uncompressed_bytes} bytes)."
            )

        compressed_size = max(info.compress_size, 1)
        expected_ratio = info.file_size / compressed_size
        if info.file_size > 1024 * 1024 and expected_ratio > self.settings.max_ratio:
            raise SecurityError(
                f"Decompression bomb detected in '{member_name}': expected ratio "
                f"{expected_ratio:.1f} exceeds threshold ({self.settings.max_ratio})."
            )

        chunks: list[bytes] = []
        total_read = 0
        chunk_size = 64 * 1024

        with zf.open(info, "r") as stream:
            while True:
                chunk = stream.read(chunk_size)
                if not chunk:
                    break
                total_read += len(chunk)
                if total_read > self.settings.max_uncompressed_bytes:
                    raise SecurityError(
                        f"Uncompressed bytes for '{member_name}' exceeded "
                        f"maximum limit ({self.settings.max_uncompressed_bytes} bytes)."
                    )
                # Check ratio periodically for large files
                if total_read > 1024 * 1024:
                    current_ratio = total_read / compressed_size
                    if current_ratio > self.settings.max_ratio:
                        raise SecurityError(
                            f"Decompression bomb detected while streaming '{member_name}': "
                            f"ratio {current_ratio:.1f} exceeds threshold."
                        )
                chunks.append(chunk)

        return b"".join(chunks)


class BaseImporter(ABC):
    """Abstract base class for vendor conversation archive importers."""

    name: str

    def __init__(self, settings: ImporterSettings | None = None) -> None:
        self.settings = settings or ImporterSettings()
        self.guard = ArchiveGuard(self.settings)

    @abstractmethod
    def list_sessions(self, archive_path: Path) -> list[SessionSummary]:
        """List all conversation sessions available in the export archive."""

    @abstractmethod
    def extract_session(
        self,
        archive_path: Path,
        session_id: str,
        project: str = "default",
    ) -> Packet:
        """Extract a specific conversation session and convert it into a Packet."""

    @abstractmethod
    def extract_all(
        self,
        archive_path: Path,
        project: str = "default",
    ) -> list[Packet]:
        """Extract all conversation sessions from the export archive as Packets."""
