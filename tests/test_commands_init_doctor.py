"""
Unit and integration tests for 'swallo init' and 'swallo doctor' CLI commands.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import TypeAdapter

from swallo.cli import main

_DICT_ADAPTER = TypeAdapter(dict)


def test_init_and_doctor_flow(tmp_path: Path) -> None:
    store_dir = tmp_path / "custom_store"

    # Step 1: Doctor before init should fail
    rc_doc_before = main(["doctor", "--store", str(store_dir), "--json"])
    assert rc_doc_before != 0

    # Step 2: Init custom store
    rc_init = main(["init", "--store", str(store_dir), "--project", "DemoApp", "--json"])
    assert rc_init == 0

    key_file = store_dir / "key"
    db_file = store_dir / "swallo.db"
    cfg_file = store_dir / "config.toml"

    assert store_dir.is_dir()
    assert key_file.is_file() and len(key_file.read_bytes()) == 32
    assert db_file.is_file()
    assert cfg_file.is_file()

    # Step 3: Doctor after init should pass
    rc_doc_after = main(["doctor", "--store", str(store_dir), "--json"])
    assert rc_doc_after == 0


def test_init_already_exists_fails_without_force(tmp_path: Path) -> None:
    store_dir = tmp_path / "custom_store"
    assert main(["init", "--store", str(store_dir), "--project", "DemoApp"]) == 0

    # Running init again without --force in non-interactive environment should fail
    rc_second = main(["init", "--store", str(store_dir)])
    assert rc_second == 2

    # Running with --force should succeed
    rc_force = main(["init", "--store", str(store_dir), "--force"])
    assert rc_force == 0


def test_doctor_json_output_schema(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store_dir = tmp_path / "custom_store"
    main(["init", "--store", str(store_dir), "--json"])
    capsys.readouterr()  # clear buffer

    main(["doctor", "--store", str(store_dir), "--json"])
    out = capsys.readouterr().out
    data = _DICT_ADAPTER.validate_json(out)

    assert data["status"] == "OK"
    assert data["store_dir"] == str(store_dir.resolve())
    assert isinstance(data["checks"], list)
    check_names = {c["name"] for c in data["checks"]}
    assert "store_directory" in check_names
    assert "key_file" in check_names
    assert "database" in check_names
    assert "event_log_integrity" in check_names


def test_doctor_detects_corrupted_key(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store_dir = tmp_path / "custom_store"
    assert main(["init", "--store", str(store_dir), "--json"]) == 0
    capsys.readouterr()

    # Corrupt key file to invalid length
    key_file = store_dir / "key"
    key_file.write_bytes(b"too_short_key")

    rc = main(["doctor", "--store", str(store_dir), "--json"])
    assert rc != 0
    out = capsys.readouterr().out
    data = _DICT_ADAPTER.validate_json(out)
    assert data["status"] == "FAIL"
    key_checks = [c for c in data["checks"] if c["name"] == "key_file"]
    assert len(key_checks) == 1
    assert key_checks[0]["status"] == "FAIL"
