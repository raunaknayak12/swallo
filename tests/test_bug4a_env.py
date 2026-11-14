"""
Bug 4a regression tests: SWALLO_STORAGE_DIR alias and SWALLO_* env var handling.

Tests:
- SWALLO_STORAGE_DIR used when SWALLO_HOME is unset
- SWALLO_HOME takes precedence when both are set, with warning to stderr if different
- Both set to same path works without warning
"""

from __future__ import annotations

from pathlib import Path

import pytest

from swallo.config import get_store_dir


def test_swallo_storage_dir_alias(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage_dir = tmp_path / "custom_storage"
    monkeypatch.delenv("SWALLO_HOME", raising=False)
    monkeypatch.setenv("SWALLO_STORAGE_DIR", str(storage_dir))

    resolved = get_store_dir()
    assert resolved == storage_dir.resolve()


def test_swallo_home_and_storage_dir_differ_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    home_dir = tmp_path / "home_dir"
    storage_dir = tmp_path / "storage_dir"

    monkeypatch.setenv("SWALLO_HOME", str(home_dir))
    monkeypatch.setenv("SWALLO_STORAGE_DIR", str(storage_dir))

    resolved = get_store_dir()
    assert resolved == home_dir.resolve()

    captured = capsys.readouterr()
    assert "Warning: Both SWALLO_HOME and SWALLO_STORAGE_DIR are set and differ" in captured.err


def test_swallo_home_and_storage_dir_same_no_warn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    same_dir = tmp_path / "same_dir"
    monkeypatch.setenv("SWALLO_HOME", str(same_dir))
    monkeypatch.setenv("SWALLO_STORAGE_DIR", str(same_dir))

    resolved = get_store_dir()
    assert resolved == same_dir.resolve()

    captured = capsys.readouterr()
    assert captured.err == ""


def test_unrecognized_swallo_env_var_hint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setenv("SWALLO_UNKNOWN_SETTING", "123")
    get_store_dir()
    captured = capsys.readouterr()
    assert "Hint: Unrecognized environment variable 'SWALLO_UNKNOWN_SETTING'" in captured.err
