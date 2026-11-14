"""
Deterministic staleness and repository drift detection for swallo.

Per TRD.md section 9.1, IMPLEMENTATION_PLAN.md Step 7, and Security.md F18:
- Compares packet's recorded repo_state against current git HEAD and filesystem.
- Critical drift triggers:
  1. Referenced file modified (content hash differs from packet's hash).
  2. Referenced file deleted.
  3. Referenced file renamed (detected via git status).
  4. Packet commit is not an ancestor of current HEAD (e.g. rebase, branch switch).
- Does NOT trigger on:
  - Unrelated commits modifying unreferenced files.
  - Non-git directories (skips with an informational note).
- Expiring acknowledgment verification against `stale_acks` table.
"""

from __future__ import annotations

import enum
import hashlib
import hmac
import os
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from swallo.repo.gitstate import (
    get_git_commit,
    hash_git_object,
    is_ancestor,
    is_git_repository,
)
from swallo.schema.canonical import packet_hash
from swallo.schema.models import Packet


class DriftType(enum.StrEnum):
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"
    DIVERGED_COMMIT = "diverged_commit"


@dataclass(frozen=True)
class DriftItem:
    path: str
    drift_type: DriftType
    expected_hash: str | None = None
    current_hash: str | None = None
    new_path: str | None = None


@dataclass
class StalenessReport:
    is_stale: bool = False
    is_critical: bool = False
    is_git_repo: bool = True
    head_commit: str | None = None
    packet_commit: str | None = None
    drifts: list[DriftItem] = field(default_factory=list)
    acknowledged: bool = False
    drift_hash: str = ""
    detail: str = ""

    @property
    def drifted_files(self) -> list[str]:
        return [d.path for d in self.drifts]


def compute_drift_hash(drifts: list[DriftItem]) -> str:
    """Compute a deterministic hash for a set of drift items."""
    if not drifts:
        return ""
    sorted_drifts = sorted(drifts, key=lambda d: (d.path, d.drift_type.value))
    payload = "|".join(
        f"{d.path}:{d.drift_type.value}:{d.expected_hash or ''}:{d.current_hash or ''}"
        for d in sorted_drifts
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _detect_git_renames(repo_root: Path) -> dict[str, str]:
    """Return a mapping of old_path -> new_path for renamed files."""
    git_bin = shutil.which("git")
    if not git_bin:
        return {}
    try:
        res = subprocess.run(  # noqa: S603
            [git_bin, "status", "--porcelain"],
            timeout=30,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            return {}
        renames: dict[str, str] = {}
        for line in res.stdout.splitlines():
            line = line.strip()
            if line.startswith("R ") or line.startswith("RM"):
                parts = line[2:].strip().split(" -> ")
                if len(parts) == 2:
                    old_p = os.path.normpath(parts[0]).replace("\\", "/")
                    new_p = os.path.normpath(parts[1]).replace("\\", "/")
                    renames[old_p] = new_p
        return renames
    except (subprocess.SubprocessError, FileNotFoundError, PermissionError):
        return {}


def is_ack_valid(
    conn: sqlite3.Connection,
    key_bytes: bytes,
    packet_hash: str,
    head: str,
    drift_hash: str,
    ttl_seconds: int = 86400,
) -> bool:
    """Verify whether a non-expired, cryptographically valid acknowledgment exists."""
    cursor = conn.cursor()
    try:
        query = (
            "SELECT acked_at, mac FROM stale_acks "
            "WHERE packet_hash = ? AND head = ? AND drift_hash = ?"
        )
        cursor.execute(query, (packet_hash, head, drift_hash))
        row = cursor.fetchone()
        if not row:
            return False

        acked_at_str, stored_mac = row[0], row[1]

        # Verify HMAC
        expected_mac = hmac.new(
            key_bytes,
            f"ack:{packet_hash}:{head}:{drift_hash}:{acked_at_str}".encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(stored_mac, expected_mac):
            return False

        # Verify TTL
        acked_dt = datetime.fromisoformat(acked_at_str)
        now = datetime.now(UTC)
        if (now - acked_dt).total_seconds() > ttl_seconds:
            return False

        return True
    except Exception:
        return False
    finally:
        cursor.close()


def record_stale_ack(
    conn: sqlite3.Connection,
    key_bytes: bytes,
    packet_hash: str,
    head: str,
    drift_hash: str,
) -> str:
    """Record an acknowledgment in the stale_acks table."""
    now_str = datetime.now(UTC).isoformat()
    mac = hmac.new(
        key_bytes,
        f"ack:{packet_hash}:{head}:{drift_hash}:{now_str}".encode(),
        hashlib.sha256,
    ).hexdigest()

    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT OR REPLACE INTO stale_acks (packet_hash, head, drift_hash, acked_at, mac)
            VALUES (?, ?, ?, ?, ?)
            """,
            (packet_hash, head, drift_hash, now_str, mac),
        )
    finally:
        cursor.close()
    return mac


def check_staleness(
    packet: Packet,
    repo_root: Path | str,
    conn: sqlite3.Connection | None = None,
    key_bytes: bytes | None = None,
    ttl_seconds: int = 86400,
    packet_hash_val: str | None = None,
) -> StalenessReport:
    """
    Check if a packet has drifted from the current repository state.
    Returns a deterministic StalenessReport.
    """
    repo_path = Path(repo_root).resolve()

    if packet.repo_state is None:
        return StalenessReport(
            is_stale=False,
            is_critical=False,
            is_git_repo=False,
            detail="No repo_state recorded in packet.",
        )

    if not is_git_repository(repo_path):
        return StalenessReport(
            is_stale=False,
            is_critical=False,
            is_git_repo=False,
            detail="Target directory is not a git repository.",
        )

    head = get_git_commit(repo_path)
    if not head:
        return StalenessReport(
            is_stale=False,
            is_critical=False,
            is_git_repo=True,
            detail="Could not determine git HEAD commit.",
        )

    drifts: list[DriftItem] = []
    pkt_commit = packet.repo_state.git_commit

    # 1. Ancestry check: packet commit must be an ancestor of HEAD
    if pkt_commit != head and not is_ancestor(repo_path, pkt_commit, head):
        drifts.append(
            DriftItem(
                path="<git_history>",
                drift_type=DriftType.DIVERGED_COMMIT,
                expected_hash=pkt_commit,
                current_hash=head,
            )
        )

    # 2. Check referenced files from repo_state
    renames = _detect_git_renames(repo_path)
    for rel_path, expected_hash in packet.repo_state.files.items():
        norm_rel = os.path.normpath(rel_path).replace("\\", "/")
        target = repo_path / norm_rel

        if norm_rel in renames:
            drifts.append(
                DriftItem(
                    path=norm_rel,
                    drift_type=DriftType.RENAMED,
                    expected_hash=expected_hash,
                    new_path=renames[norm_rel],
                )
            )
        elif not target.is_file():
            drifts.append(
                DriftItem(
                    path=norm_rel,
                    drift_type=DriftType.DELETED,
                    expected_hash=expected_hash,
                )
            )
        else:
            curr_hash = hash_git_object(repo_path, norm_rel)
            if curr_hash != expected_hash:
                drifts.append(
                    DriftItem(
                        path=norm_rel,
                        drift_type=DriftType.MODIFIED,
                        expected_hash=expected_hash,
                        current_hash=curr_hash,
                    )
                )

    is_stale = len(drifts) > 0
    drift_hash = compute_drift_hash(drifts)
    acknowledged = False

    if is_stale and conn is not None and key_bytes is not None:
        p_hash = (
            packet_hash_val
            if packet_hash_val is not None
            else packet_hash(packet.model_dump(exclude_none=True))
        )
        acknowledged = is_ack_valid(
            conn=conn,
            key_bytes=key_bytes,
            packet_hash=p_hash,
            head=head,
            drift_hash=drift_hash,
            ttl_seconds=ttl_seconds,
        )

    is_critical = is_stale and not acknowledged

    if not is_stale:
        detail = "Repository state is up to date."
    elif acknowledged:
        detail = f"Drift detected ({len(drifts)} items) but verified with active acknowledgment."
    else:
        drift_names = ", ".join(d.path for d in drifts[:3])
        if len(drifts) > 3:
            drift_names += f" and {len(drifts) - 3} more"
        detail = f"Critical drift detected: {drift_names}"

    return StalenessReport(
        is_stale=is_stale,
        is_critical=is_critical,
        is_git_repo=True,
        head_commit=head,
        packet_commit=pkt_commit,
        drifts=drifts,
        acknowledged=acknowledged,
        drift_hash=drift_hash,
        detail=detail,
    )
