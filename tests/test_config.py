"""
Unit tests for store location helper and config loader.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from swallo.config import (
    get_default_config_template,
    get_store_dir,
    is_inside_git_worktree,
    load_config,
)


def test_store_dir_explicit_override(tmp_path: Path) -> None:
    custom = tmp_path / "custom_store"
    assert get_store_dir(custom) == custom.resolve()


def test_store_dir_swallo_home_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_dir = tmp_path / "env_store"
    monkeypatch.setenv("SWALLO_HOME", str(env_dir))
    assert get_store_dir() == env_dir.resolve()


def test_store_dir_windows_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SWALLO_HOME", raising=False)
    fake_local = r"C:\Users\FakeUser\AppData\Local"
    monkeypatch.setenv("LOCALAPPDATA", fake_local)

    with patch("sys.platform", "win32"):
        expected = Path(fake_local) / "swallo"
        assert get_store_dir() == expected.resolve()


def test_store_dir_darwin_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SWALLO_HOME", raising=False)
    fake_home = Path("/Users/FakeUser")

    with patch("sys.platform", "darwin"), patch.object(Path, "home", return_value=fake_home):
        expected = fake_home / "Library" / "Application Support" / "swallo"
        assert get_store_dir() == expected.resolve()


def test_store_dir_linux_xdg_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SWALLO_HOME", raising=False)
    fake_xdg = "/home/fakeuser/.custom_data"
    monkeypatch.setenv("XDG_DATA_HOME", fake_xdg)

    with patch("sys.platform", "linux"):
        expected = Path(fake_xdg) / "swallo"
        assert get_store_dir() == expected.resolve()


def test_load_config_default_when_missing(tmp_path: Path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    cfg, warnings = load_config(store)
    assert cfg.redact.mode == "fail_closed"
    assert cfg.delivery.mode == "two_file"
    assert cfg.trust.ide_agent_autoapprove is False
    assert len(warnings) == 0


def test_load_config_with_custom_file(tmp_path: Path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    config_file = store / "config.toml"
    config_file.write_text(
        """
[redact]
mode = "warn"
denylist = ["SECRET_TOKEN", "API_KEY"]

[budget]
default_tokens = 8000
""",
        encoding="utf-8",
    )

    cfg, warnings = load_config(store)
    assert cfg.redact.mode == "warn"
    assert cfg.redact.denylist == ["SECRET_TOKEN", "API_KEY"]
    assert cfg.budget.default_tokens == 8000
    assert len(warnings) == 0


def test_load_config_warns_on_unknown_keys(tmp_path: Path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    config_file = store / "config.toml"
    config_file.write_text(
        """
[unknown_section]
bogus_field = 123

[redact]
unexpected_key = "value"
""",
        encoding="utf-8",
    )

    cfg, warnings = load_config(store)
    assert any("unknown_section" in w for w in warnings)
    assert any("unexpected_key" in w for w in warnings)


def test_is_inside_git_worktree(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()
    nested_dir = repo_dir / "subdir" / "store"
    nested_dir.mkdir(parents=True)

    assert is_inside_git_worktree(nested_dir) is True
    assert is_inside_git_worktree(tmp_path) is False


def test_get_default_config_template_valid() -> None:
    import tomllib
    template = get_default_config_template()
    parsed = tomllib.loads(template)
    assert "redact" in parsed
    assert "mcp" in parsed


def test_autoapprove_cannot_be_enabled_in_config(tmp_path: Path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    config_file = store / "config.toml"
    config_file.write_text(
        """
[trust]
ide_agent_autoapprove = true
""",
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="ide_agent_autoapprove cannot be enabled"):
        load_config(store)
