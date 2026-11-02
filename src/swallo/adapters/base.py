"""
Base adapter protocol and target delivery result models.

Per TRD.md section 7 and IMPLEMENTATION_PLAN.md Step 5:
- All adapters write exclusively within the project root via the shared path resolver.
- Enforces two-file delivery pattern (handoff file + stub block).
- Returns DeliveryResult with relative file paths and hashes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class DeliveryResult:
    target: str
    packet_id: str
    handoff_path: str
    stub_path: str
    handoff_hash: str
    stub_hash: str
    token_count: int


class BaseAdapter(Protocol):
    """Protocol for target environment adapters (e.g. Claude Code, Cursor, Chat)."""

    name: str

    def deliver(
        self,
        project_root: Path,
        packet_data: dict[str, Any],
        token_budget: int = 4000,
    ) -> DeliveryResult:
        """
        Deliver a context packet to the target project using the two-file pattern.

        Args:
            project_root: Absolute root path of the project.
            packet_data: Canonical packet dictionary.
            token_budget: Maximum tokens allowed for the handoff document.

        Returns:
            DeliveryResult recording the relative paths and hashes of written files.
        """
        ...


def update_marker_block(
    file_content: str,
    begin_marker: str,
    end_marker: str,
    new_block_body: str,
) -> str:
    """
    Idempotently update a marker block inside a file.

    If the markers exist, the content between them is replaced.
    If the markers do not exist, the block is appended to the file.
    All surrounding content outside the markers is strictly preserved.
    """
    block = f"{begin_marker}\n{new_block_body.strip()}\n{end_marker}\n"

    if begin_marker in file_content and end_marker in file_content:
        start_idx = file_content.find(begin_marker)
        end_idx = file_content.find(end_marker) + len(end_marker)
        # Check if there is a trailing newline after the end marker
        if end_idx < len(file_content) and file_content[end_idx] == "\n":
            end_idx += 1
        return file_content[:start_idx] + block + file_content[end_idx:]

    # Append to file
    prefix = ""
    if file_content and not file_content.endswith("\n"):
        prefix = "\n"
    if file_content.strip():
        prefix += "\n"
    return file_content + prefix + block


def compute_file_sha256(path: Path) -> str:
    """Compute sha256:<hex> of a file."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return f"sha256:{h.hexdigest()}"
