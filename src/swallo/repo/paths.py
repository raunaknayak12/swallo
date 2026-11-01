"""
Repository-relative path confinement and path traversal defense for swallo.

Per TRD.md section 6.5, IMPLEMENTATION_PLAN.md Step 3, and Security.md F4:
- All repository file access must pass through resolve_in_root.
- Rejects absolute paths, '..' traversal components, null bytes, alternate data streams.
- Rejects symlink escapes pointing outside the repository root boundary.
"""

from __future__ import annotations

import re
from pathlib import Path

from swallo.errors import SecurityError, ValidationError

# Regex to detect Windows drive prefixes (e.g. C:, D:)
_WINDOWS_DRIVE_RE = re.compile(r"^[a-zA-Z]:")


def resolve_in_root(root: Path | str, rel: str) -> Path:
    """
    Resolve a relative path inside a repository root with strict confinement.

    Raises:
        ValidationError: If rel is empty or contains null bytes.
        SecurityError: If rel attempts to escape the root boundary via absolute paths,
                       '..' components, symlinks, or alternate data streams.
    """
    if not isinstance(rel, str) or not rel.strip():
        raise ValidationError("Relative path cannot be empty")

    if "\0" in rel:
        raise ValidationError("Null bytes forbidden in path")

    # Reject leading slashes or Windows backslashes
    if rel.startswith(("/", "\\")):
        raise SecurityError(f"Absolute paths forbidden: {rel}")

    # Reject Windows drive letters
    if _WINDOWS_DRIVE_RE.match(rel):
        raise SecurityError(f"Drive letter prefixes forbidden: {rel}")

    # Check for '..' components or alternate data streams in any component
    normalized_parts = re.split(r"[/\\]+", rel.strip())
    for part in normalized_parts:
        if part == "..":
            raise SecurityError(f"Parent directory traversal '..' forbidden: {rel}")
        if ":" in part:
            raise SecurityError(f"Alternate data streams or drive colons forbidden: {rel}")

    root_resolved = Path(root).resolve()

    # Construct target path
    candidate = root_resolved
    for part in normalized_parts:
        if part and part != ".":
            candidate = candidate / part

    # Resolve symlinks and check confinement
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        raise SecurityError(
            f"Path traversal detected: '{rel}' escapes root '{root_resolved}'"
        ) from None

    # Even if file doesn't exist yet, check all existing ancestors to ensure
    # intermediate symlinks didn't point outside root
    check_ancestor = candidate
    while not check_ancestor.exists() and check_ancestor != root_resolved:
        parent = check_ancestor.parent
        if parent == check_ancestor:
            break
        check_ancestor = parent

    if check_ancestor.exists():
        ancestor_resolved = check_ancestor.resolve()
        try:
            ancestor_resolved.relative_to(root_resolved)
        except ValueError:
            raise SecurityError(
                f"Symlink ancestor escape detected: '{rel}' escapes root '{root_resolved}'"
            ) from None

    return resolved


def to_repo_relative(root: Path | str, path: Path | str) -> str:
    """
    Convert a path inside root to a clean, forward-slash POSIX-style relative path string.

    Raises:
        SecurityError: If path is not inside root.
    """
    root_resolved = Path(root).resolve()
    path_resolved = Path(path).resolve()

    try:
        rel = path_resolved.relative_to(root_resolved)
    except ValueError:
        raise SecurityError(
            f"Path '{path_resolved}' is not located inside root '{root_resolved}'"
        ) from None

    return rel.as_posix()
