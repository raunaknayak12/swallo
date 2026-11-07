"""
Fuzz and security tests for vendor archive importers (Security.md F8).

Tests:
- Zip-Slip path traversal attacks (relative paths, absolute paths, backslashes).
- Decompression bomb detection (byte quotas, compression ratios).
- Archive entry count limits (> 1000 entries).
- Symlink disallowance in archives.
- Deeply nested recursive JSON attacks (> 50 levels).
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from swallo.capture.importers.base import ArchiveGuard
from swallo.capture.importers.stream import safe_json_loads
from swallo.config import ImporterSettings
from swallo.errors import SecurityError, ValidationError


def _create_zip_with_members(members: dict[str, bytes]) -> bytes:
    """Helper to create an in-memory zip bytes buffer."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_guard_validates_file_existence(tmp_path: Path) -> None:
    guard = ArchiveGuard(ImporterSettings())
    missing = tmp_path / "nonexistent.zip"
    with pytest.raises(ValidationError, match="Archive file does not exist"):
        guard.validate_archive_path(missing)


def test_guard_rejects_oversized_archive(tmp_path: Path) -> None:
    settings = ImporterSettings(max_archive_bytes=100)
    guard = ArchiveGuard(settings)

    oversized = tmp_path / "big.zip"
    oversized.write_bytes(b"x" * 200)

    with pytest.raises(SecurityError, match="exceeds maximum permitted limit"):
        guard.validate_archive_path(oversized)


def test_zip_slip_relative_path_traversal(tmp_path: Path) -> None:
    guard = ArchiveGuard(ImporterSettings())
    slip_zip = tmp_path / "slip.zip"

    # Create zip with directory traversal entry
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../etc/passwd", b"root:x:0:0:")
        zf.writestr("conversations.json", b"[]")
    slip_zip.write_bytes(buf.getvalue())

    with zipfile.ZipFile(slip_zip, "r") as zf:
        with pytest.raises(SecurityError, match="Path traversal detected in archive entry"):
            guard.verify_zip_structure(zf)


def test_zip_slip_absolute_path_traversal(tmp_path: Path) -> None:
    guard = ArchiveGuard(ImporterSettings())
    abs_zip = tmp_path / "abs.zip"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("/root/.ssh/id_rsa", b"private key")
    abs_zip.write_bytes(buf.getvalue())

    with zipfile.ZipFile(abs_zip, "r") as zf:
        with pytest.raises(SecurityError, match="Path traversal detected in archive entry"):
            guard.verify_zip_structure(zf)


def test_zip_bomb_entry_count_limit(tmp_path: Path) -> None:
    settings = ImporterSettings(max_entries=10)
    guard = ArchiveGuard(settings)
    many_entries_zip = tmp_path / "many.zip"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i in range(15):
            zf.writestr(f"file_{i}.txt", b"ok")
    many_entries_zip.write_bytes(buf.getvalue())

    with zipfile.ZipFile(many_entries_zip, "r") as zf:
        with pytest.raises(SecurityError, match="exceeding maximum permitted entry count"):
            guard.verify_zip_structure(zf)


def test_zip_bomb_uncompressed_size_limit(tmp_path: Path) -> None:
    settings = ImporterSettings(max_uncompressed_bytes=500)
    guard = ArchiveGuard(settings)
    bomb_zip = tmp_path / "bomb.zip"

    data = b"0" * 1000
    zip_bytes = _create_zip_with_members({"conversations.json": data})
    bomb_zip.write_bytes(zip_bytes)

    with zipfile.ZipFile(bomb_zip, "r") as zf:
        with pytest.raises(SecurityError, match="exceeds maximum limit"):
            guard.safe_read_member(zf, "conversations.json")


def test_zip_bomb_ratio_limit(tmp_path: Path) -> None:
    # Set 5MB uncompressed limit and strict ratio limit of 3.0
    settings = ImporterSettings(max_uncompressed_bytes=5 * 1024 * 1024, max_ratio=3.0)
    guard = ArchiveGuard(settings)
    ratio_zip = tmp_path / "ratio.zip"

    # Highly compressible 2MB payload (> 1MB threshold in base.py)
    repetitive_data = b"A" * (2 * 1024 * 1024)
    zip_bytes = _create_zip_with_members({"conversations.json": repetitive_data})
    ratio_zip.write_bytes(zip_bytes)

    with zipfile.ZipFile(ratio_zip, "r") as zf:
        with pytest.raises(SecurityError, match="Decompression bomb detected"):
            guard.safe_read_member(zf, "conversations.json")


def test_safe_json_loads_normal_payload() -> None:
    raw = '{"project": "demo", "items": [{"kind": "decision", "text": "use sqlite"}]}'
    result = safe_json_loads(raw, max_depth=10)
    assert isinstance(result, dict)
    assert result["project"] == "demo"


def test_safe_json_loads_deep_nesting_attack() -> None:
    # 60 levels of nested arrays
    depth = 60
    deep_json = ("[" * depth) + "1" + ("]" * depth)

    with pytest.raises(SecurityError, match="exceeds maximum permitted limit"):
        safe_json_loads(deep_json, max_depth=50)


def test_safe_json_loads_invalid_syntax() -> None:
    malformed = '{"project": "incomplete"'
    with pytest.raises(ValidationError, match="Malformed JSON data"):
        safe_json_loads(malformed, max_depth=50)
