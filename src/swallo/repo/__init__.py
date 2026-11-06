"""
Repository, git-state, and path security helpers for swallo.
"""

from swallo.repo.gitstate import (
    compute_git_blob_hash,
    get_git_commit,
    get_repo_state,
    hash_git_object,
    is_ancestor,
    is_git_dirty,
    is_git_repository,
)
from swallo.repo.paths import resolve_in_root
from swallo.repo.staleness import (
    DriftItem,
    DriftType,
    StalenessReport,
    check_staleness,
    compute_drift_hash,
    is_ack_valid,
    record_stale_ack,
)

__all__ = [
    "DriftItem",
    "DriftType",
    "StalenessReport",
    "check_staleness",
    "compute_drift_hash",
    "compute_git_blob_hash",
    "get_git_commit",
    "get_repo_state",
    "hash_git_object",
    "is_ack_valid",
    "is_ancestor",
    "is_git_dirty",
    "is_git_repository",
    "record_stale_ack",
    "resolve_in_root",
]
