"""Tests for adapter base utilities: marker block and file hashing."""

from __future__ import annotations

import hashlib
from pathlib import Path

from swallo.adapters.base import compute_file_sha256, update_marker_block


class TestUpdateMarkerBlock:
    """Tests for idempotent marker block insertion/replacement."""

    BEGIN = "<!-- swallo:begin pkt_abc123 -->"
    END = "<!-- swallo:end pkt_abc123 -->"
    BODY = "Read .swallo/handoff/abc123.md for context."

    def test_insert_into_empty_file(self) -> None:
        result = update_marker_block("", self.BEGIN, self.END, self.BODY)
        assert self.BEGIN in result
        assert self.END in result
        assert self.BODY in result

    def test_insert_appends_to_existing_content(self) -> None:
        existing = "# CLAUDE.md\n\nSome existing rules.\n"
        result = update_marker_block(existing, self.BEGIN, self.END, self.BODY)
        # Existing content preserved
        assert result.startswith("# CLAUDE.md\n\nSome existing rules.\n")
        # New block appended
        assert self.BEGIN in result
        assert self.BODY in result
        assert self.END in result

    def test_replace_existing_block(self) -> None:
        old_body = "Old content here."
        new_body = "New content here."
        content = (
            "# CLAUDE.md\n\n"
            f"{self.BEGIN}\n{old_body}\n{self.END}\n"
            "\nMore rules below.\n"
        )
        result = update_marker_block(content, self.BEGIN, self.END, new_body)
        assert new_body in result
        assert old_body not in result
        # Surrounding content preserved
        assert result.startswith("# CLAUDE.md\n\n")
        assert result.endswith("\nMore rules below.\n")

    def test_preserves_content_before_and_after_markers(self) -> None:
        before = "Line before marker.\n"
        after = "Line after marker.\n"
        content = (
            before
            + f"{self.BEGIN}\nold stuff\n{self.END}\n"
            + after
        )
        result = update_marker_block(content, self.BEGIN, self.END, "new stuff")
        assert result.startswith(before)
        assert result.endswith(after)

    def test_idempotent_double_update(self) -> None:
        first = update_marker_block("", self.BEGIN, self.END, self.BODY)
        second = update_marker_block(first, self.BEGIN, self.END, self.BODY)
        assert first == second

    def test_multiple_different_markers_coexist(self) -> None:
        begin_a = "<!-- swallo:begin pkt_aaa -->"
        end_a = "<!-- swallo:end pkt_aaa -->"
        begin_b = "<!-- swallo:begin pkt_bbb -->"
        end_b = "<!-- swallo:end pkt_bbb -->"

        content = update_marker_block("# Rules\n", begin_a, end_a, "Block A")
        content = update_marker_block(content, begin_b, end_b, "Block B")
        assert "Block A" in content
        assert "Block B" in content
        assert begin_a in content
        assert begin_b in content


class TestComputeFileSha256:
    """Tests for SHA-256 file hashing."""

    def test_hash_matches_manual(self, tmp_path: Path) -> None:
        p = tmp_path / "test.txt"
        data = b"hello world\n"
        p.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        expected = f"sha256:{digest}"
        assert compute_file_sha256(p) == expected

    def test_empty_file(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.txt"
        p.write_bytes(b"")
        result = compute_file_sha256(p)
        assert result.startswith("sha256:")
        assert len(result) == len("sha256:") + 64
