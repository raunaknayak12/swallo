"""
Deterministic Defense Matrix Benchmark.

Evaluates security boundary defenses against hostile payloads.

Design note per ADR-022 and TRD.md:
- `ArchiveGuard.verify_zip_structure()` checks: entry count, path traversal (Zip-Slip), symlinks.
- `ArchiveGuard.safe_read_member()` checks: declared uncompressed size limit, decompression ratio
  (only triggers when file_size > 1 MB), and streaming byte cap.
- `safe_json_loads()` checks: JSON nesting depth.
Tests reflect the actual API contracts, not assumed behavior.

Attack vectors tested:
- Zip-Slip directory traversal (relative ../.. , absolute /etc/, backslash ..\\..)
- Member count limit (> max_entries)
- Declared size limit (> max_uncompressed_bytes) via safe_read_member
- Synthetic zip bomb (> max_ratio:1) via safe_read_member; generated synthetically, never committed
- JSON nesting depth > max_json_depth
"""

from __future__ import annotations

import io
import zipfile
from typing import Any

from swallo.capture.importers.base import ArchiveGuard
from swallo.capture.importers.stream import safe_json_loads
from swallo.config import ImporterSettings
from swallo.errors import SecurityError


def evaluate_defense_matrix() -> dict[str, Any]:
    """Execute defense matrix checks and verify all attacks are blocked."""
    results: dict[str, Any] = {}

    # 1. Zip-Slip Relative Traversal (verify_zip_structure)
    buf_rel = io.BytesIO()
    with zipfile.ZipFile(buf_rel, "w") as zf:
        zf.writestr("../../etc/shadow", b"root:x:0:0:")
    buf_rel.seek(0)
    with zipfile.ZipFile(buf_rel, "r") as zf:
        try:
            ArchiveGuard().verify_zip_structure(zf)
            rel_blocked = False
        except SecurityError:
            rel_blocked = True
    results["zip_slip_relative_blocked"] = rel_blocked

    # 2. Zip-Slip Absolute Path Traversal (verify_zip_structure)
    buf_abs = io.BytesIO()
    with zipfile.ZipFile(buf_abs, "w") as zf:
        zf.writestr("/etc/passwd", b"root:x:0:0:")
    buf_abs.seek(0)
    with zipfile.ZipFile(buf_abs, "r") as zf:
        try:
            ArchiveGuard().verify_zip_structure(zf)
            abs_blocked = False
        except SecurityError:
            abs_blocked = True
    results["zip_slip_absolute_blocked"] = abs_blocked

    # 3. Zip-Slip Backslash Traversal (Windows style ..\..\ — verify_zip_structure)
    buf_bs = io.BytesIO()
    with zipfile.ZipFile(buf_bs, "w") as zf:
        zf.writestr("..\\..\\Windows\\System32\\cmd.exe", b"malicious")
    buf_bs.seek(0)
    with zipfile.ZipFile(buf_bs, "r") as zf:
        try:
            ArchiveGuard().verify_zip_structure(zf)
            bs_blocked = False
        except SecurityError:
            bs_blocked = True
    results["zip_slip_backslash_blocked"] = bs_blocked

    # 4. Member Count Limit (verify_zip_structure)
    strict_guard_members = ArchiveGuard(ImporterSettings(max_entries=100))
    buf_members = io.BytesIO()
    with zipfile.ZipFile(buf_members, "w") as zf:
        for i in range(120):
            zf.writestr(f"item_{i}.txt", b"x")
    buf_members.seek(0)
    with zipfile.ZipFile(buf_members, "r") as zf:
        try:
            strict_guard_members.verify_zip_structure(zf)
            members_blocked = False
        except SecurityError:
            members_blocked = True
    results["member_count_limit_blocked"] = members_blocked

    # 5. Declared Size Limit (safe_read_member — checks info.file_size before decompression)
    # Set a 1 KB max; write a member that declares 2 KB of content.
    strict_size_guard = ArchiveGuard(ImporterSettings(max_uncompressed_bytes=1024))
    buf_size = io.BytesIO()
    with zipfile.ZipFile(buf_size, "w") as zf:
        zf.writestr("oversized.txt", b"A" * 2048)
    buf_size.seek(0)
    with zipfile.ZipFile(buf_size, "r") as zf:
        try:
            strict_size_guard.safe_read_member(zf, "oversized.txt")
            size_blocked = False
        except SecurityError:
            size_blocked = True
    results["uncompressed_size_limit_blocked"] = size_blocked

    # 6. Decompression Bomb Ratio (safe_read_member)
    # Synthetic bomb: 2 MB of zeroes (compresses >500:1); max_ratio=1.5 so it triggers.
    # The file_size > 1 MB check gate in safe_read_member requires the declared size to exceed 1 MB.
    # Never committed to disk — generated synthetically in memory per Hard Rule #2 amendment.
    bomb_guard = ArchiveGuard(ImporterSettings(max_ratio=1.5, max_uncompressed_bytes=10 * 1024 * 1024))
    buf_bomb = io.BytesIO()
    with zipfile.ZipFile(buf_bomb, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("bomb.bin", b"\x00" * (2 * 1024 * 1024))  # 2 MB zeroes
    buf_bomb.seek(0)
    with zipfile.ZipFile(buf_bomb, "r") as zf:
        try:
            bomb_guard.safe_read_member(zf, "bomb.bin")
            bomb_blocked = False
        except SecurityError:
            bomb_blocked = True
    results["compression_ratio_bomb_blocked"] = bomb_blocked

    # 7. Deeply Nested JSON Depth (> max_json_depth)
    deep_json = '{"a": ' * 70 + "1" + "}" * 70
    try:
        safe_json_loads(deep_json, max_depth=64)
        depth_blocked = False
    except SecurityError:
        depth_blocked = True
    results["json_max_depth_blocked"] = depth_blocked

    results["defense_matrix_pass_rate"] = 1.0 if all(results.values()) else 0.0
    return results
