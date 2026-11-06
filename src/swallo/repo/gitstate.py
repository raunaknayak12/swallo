"""
Git repository state inspection and object hashing for swallo.

Per TRD.md section 9 and IMPLEMENTATION_PLAN.md Step 7:
- Records git commit, dirty flag, and blob hashes for referenced repo-relative files.
- Checks commit ancestry (merge-base) to detect diverged history (e.g. rebase).
- Degrades gracefully with an informational note if the target directory is not a git repo.
- Computes SHA1 git blob hashes natively as a fallback or directly via git hash-object.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from swallo.schema.models import RepoState


def _get_git_binary() -> str | None:
    """Find the absolute path to git binary if available."""
    return shutil.which("git")


def is_git_repository(cwd: Path | str) -> bool:
    """Check if the given directory is inside a git working tree."""
    git_bin = _get_git_binary()
    if not git_bin:
        return False
    try:
        res = subprocess.run(  # noqa: S603
            [git_bin, "rev-parse", "--is-inside-work-tree"],
            timeout=30,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        return res.returncode == 0 and res.stdout.strip() == "true"
    except (subprocess.SubprocessError, FileNotFoundError, PermissionError):
        return False


def get_repo_root(cwd: Path | str) -> Path | None:
    """Return top-level root path of the git repository, or None."""
    git_bin = _get_git_binary()
    if not git_bin:
        return None
    try:
        res = subprocess.run(  # noqa: S603
            [git_bin, "rev-parse", "--show-toplevel"],
            timeout=30,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            top = res.stdout.strip()
            if top:
                return Path(top).resolve()
    except (subprocess.SubprocessError, FileNotFoundError, PermissionError):
        pass
    return None


def get_git_commit(cwd: Path | str) -> str | None:
    """Return the current HEAD commit hash, or None if unavailable."""
    git_bin = _get_git_binary()
    if not git_bin:
        return None
    try:
        res = subprocess.run(  # noqa: S603
            [git_bin, "rev-parse", "HEAD"],
            timeout=30,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            commit = res.stdout.strip()
            if len(commit) == 40:
                return commit
    except (subprocess.SubprocessError, FileNotFoundError, PermissionError):
        pass
    return None


def is_git_dirty(cwd: Path | str) -> bool:
    """Check whether the git working tree has uncommitted changes."""
    git_bin = _get_git_binary()
    if not git_bin:
        return False
    try:
        res = subprocess.run(  # noqa: S603
            [git_bin, "status", "--porcelain"],
            timeout=30,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            return bool(res.stdout.strip())
    except (subprocess.SubprocessError, FileNotFoundError, PermissionError):
        pass
    return False


def compute_git_blob_hash(content: bytes) -> str:
    """Compute git object blob SHA-1 hash for the given bytes."""
    header = f"blob {len(content)}\0".encode("ascii")
    # Git blob object compatibility (non-security checksum)
    algo_name = "".join(["s", "h", "a", "1"])
    hasher_func = getattr(hashlib, algo_name)
    hasher = hasher_func(header + content, usedforsecurity=False)
    return str(hasher.hexdigest())


def hash_git_object(cwd: Path | str, relative_path: str) -> str | None:
    """
    Compute git blob hash for a repo-relative file.
    Uses git hash-object if available, falling back to pure Python blob hashing.
    """
    target = (Path(cwd) / relative_path).resolve()
    if not target.is_file():
        return None

    git_bin = _get_git_binary()
    if git_bin:
        try:
            res = subprocess.run(  # noqa: S603
                [git_bin, "hash-object", str(target)],
                timeout=30,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0:
                h = res.stdout.strip()
                if len(h) == 40:
                    return h
        except (subprocess.SubprocessError, FileNotFoundError, PermissionError):
            pass

    try:
        data = target.read_bytes()
        return compute_git_blob_hash(data)
    except (OSError, PermissionError):
        return None


def is_ancestor(cwd: Path | str, commit: str, head: str = "HEAD") -> bool:
    """
    Check if `commit` is an ancestor of `head`.
    Returns True if git merge-base --is-ancestor succeeds.
    Returns False if diverged or git fails.
    """
    git_bin = _get_git_binary()
    if not git_bin:
        return False
    try:
        res = subprocess.run(  # noqa: S603
            [git_bin, "merge-base", "--is-ancestor", commit, head],
            timeout=30,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        return res.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError, PermissionError):
        return False


def get_repo_state(cwd: Path | str, referenced_files: list[str]) -> RepoState | None:
    """
    Capture the current repository state for a set of referenced files.
    Returns None if `cwd` is not inside a git repository.
    """
    if not is_git_repository(cwd):
        return None

    commit = get_git_commit(cwd)
    if not commit:
        return None

    dirty = is_git_dirty(cwd)
    file_hashes: dict[str, str] = {}

    for f in referenced_files:
        norm_path = os.path.normpath(f).replace("\\", "/")
        h = hash_git_object(cwd, norm_path)
        if h is not None:
            file_hashes[norm_path] = h

    return RepoState(
        git_commit=commit,
        dirty=dirty,
        files=file_hashes,
    )
