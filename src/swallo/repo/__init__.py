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

__all__ = [
    "compute_git_blob_hash",
    "get_git_commit",
    "get_repo_state",
    "hash_git_object",
    "is_ancestor",
    "is_git_dirty",
    "is_git_repository",
    "resolve_in_root",
]
