"""
Unit and property tests for repository path confinement (resolve_in_root).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from swallo.errors import SecurityError, ValidationError
from swallo.repo.paths import resolve_in_root, to_repo_relative


def test_resolve_valid_nested_path(tmp_path: Path) -> None:
    real_root = tmp_path.resolve()
    target = resolve_in_root(real_root, "docs/subfolder/file.md")
    assert target.is_relative_to(real_root)
    assert target.name == "file.md"


def test_resolve_empty_and_null_bytes(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="cannot be empty"):
        resolve_in_root(tmp_path, "")

    with pytest.raises(ValidationError, match="cannot be empty"):
        resolve_in_root(tmp_path, "   ")

    with pytest.raises(ValidationError, match="Null bytes"):
        resolve_in_root(tmp_path, "docs/\0secret.txt")


def test_resolve_rejects_absolute_paths(tmp_path: Path) -> None:
    with pytest.raises(SecurityError, match="Absolute paths forbidden"):
        resolve_in_root(tmp_path, "/etc/passwd")

    with pytest.raises(SecurityError, match="Absolute paths forbidden"):
        resolve_in_root(tmp_path, "\\Windows\\System32")

    with pytest.raises(SecurityError, match="Drive letter prefixes forbidden"):
        resolve_in_root(tmp_path, "C:/Windows")


def test_resolve_rejects_parent_traversal(tmp_path: Path) -> None:
    with pytest.raises(SecurityError, match="Parent directory traversal"):
        resolve_in_root(tmp_path, "../outside.txt")

    with pytest.raises(SecurityError, match="Parent directory traversal"):
        resolve_in_root(tmp_path, "docs/../../outside.txt")

    with pytest.raises(SecurityError, match="Parent directory traversal"):
        resolve_in_root(tmp_path, "sub/..\\..\\outside.txt")


def test_resolve_rejects_alternate_data_streams(tmp_path: Path) -> None:
    with pytest.raises(SecurityError, match="Alternate data streams"):
        resolve_in_root(tmp_path, "file.txt:hidden_stream")


def test_resolve_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path / "outside_dir"
    outside.mkdir()
    secret_file = outside / "secret.txt"
    secret_file.write_text("classified")

    inside = tmp_path / "repo_root"
    inside.mkdir()

    symlink_link = inside / "symlink_dir"
    try:
        symlink_link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation not permitted in this environment")

    with pytest.raises(SecurityError, match="Path traversal detected"):
        resolve_in_root(inside, "symlink_dir/secret.txt")


def test_to_repo_relative(tmp_path: Path) -> None:
    sub = tmp_path / "src" / "package" / "module.py"
    rel = to_repo_relative(tmp_path, sub)
    assert rel == "src/package/module.py"

    outside = tmp_path.parent / "other_file.txt"
    with pytest.raises(SecurityError, match="not located inside root"):
        to_repo_relative(tmp_path, outside)


@given(
    components=st.lists(
        st.text(
            alphabet=st.characters(
                categories=("Lu", "Ll", "Nd"),
            ),
            min_size=1,
            max_size=15,
        ),
        min_size=1,
        max_size=5,
    )
)
def test_property_safe_paths_stay_inside_root(components: list[str]) -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td).resolve()
        rel_path = "/".join(components)
        resolved = resolve_in_root(root, rel_path)
        assert resolved.is_relative_to(root)
