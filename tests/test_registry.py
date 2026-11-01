"""
Unit tests for the project root registry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from swallo.errors import ValidationError
from swallo.store.db import apply_migrations, get_connection
from swallo.store.registry import (
    find_registered_root_for_path,
    get_project,
    is_root_registered,
    list_projects,
    register_project,
    unregister_project,
)


def test_register_and_get_project(tmp_path: Path) -> None:
    db_file = tmp_path / "swallo.db"
    conn = get_connection(db_file)
    apply_migrations(conn)

    proj_dir = tmp_path / "my_project"
    proj_dir.mkdir()

    assert not is_root_registered(conn, proj_dir)

    record = register_project(conn, proj_dir, name="My App")
    assert record["name"] == "My App"
    assert is_root_registered(conn, proj_dir)

    fetched = get_project(conn, proj_dir)
    assert fetched is not None
    assert fetched["name"] == "My App"
    assert fetched["root_path"] == str(proj_dir.resolve())


def test_register_nonexistent_directory_fails(tmp_path: Path) -> None:
    db_file = tmp_path / "swallo.db"
    conn = get_connection(db_file)
    apply_migrations(conn)

    missing = tmp_path / "does_not_exist"
    with pytest.raises(ValidationError, match="nonexistent directory"):
        register_project(conn, missing)


def test_register_file_fails(tmp_path: Path) -> None:
    db_file = tmp_path / "swallo.db"
    conn = get_connection(db_file)
    apply_migrations(conn)

    file_path = tmp_path / "a_file.txt"
    file_path.write_text("content")

    with pytest.raises(ValidationError, match="must be a directory"):
        register_project(conn, file_path)


def test_list_and_unregister_projects(tmp_path: Path) -> None:
    db_file = tmp_path / "swallo.db"
    conn = get_connection(db_file)
    apply_migrations(conn)

    p1 = tmp_path / "p1"
    p2 = tmp_path / "p2"
    p1.mkdir()
    p2.mkdir()

    register_project(conn, p1, name="Project 1")
    register_project(conn, p2, name="Project 2")

    projects = list_projects(conn)
    assert len(projects) == 2

    assert unregister_project(conn, p1)
    assert not is_root_registered(conn, p1)
    assert is_root_registered(conn, p2)

    assert not unregister_project(conn, p1)


def test_find_registered_root_for_nested_path(tmp_path: Path) -> None:
    db_file = tmp_path / "swallo.db"
    conn = get_connection(db_file)
    apply_migrations(conn)

    repo_dir = tmp_path / "my_repo"
    sub_dir = repo_dir / "src" / "pkg"
    sub_dir.mkdir(parents=True)
    file_in_repo = sub_dir / "code.py"
    file_in_repo.write_text("print(1)")

    register_project(conn, repo_dir, name="My Repo")

    found = find_registered_root_for_path(conn, file_in_repo)
    assert found is not None
    assert found == repo_dir.resolve()

    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("outside")
    assert find_registered_root_for_path(conn, outside_file) is None
