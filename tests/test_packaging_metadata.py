"""
Packaging & Licensing Metadata Invariant Tests.

Verifies:
- Dual-license files (`LICENSE-MIT`, `LICENSE-APACHE`, `LICENSE`) are present and non-empty.
- Contributor Covenant Code of Conduct (`CODE_OF_CONDUCT.md`) is present.
- pyproject.toml declares SPDX `MIT OR Apache-2.0` and both OSI classifiers.
"""

from __future__ import annotations

import tomllib
from pathlib import Path


def test_license_files_exist() -> None:
    root = Path(__file__).resolve().parent.parent
    mit_license = root / "LICENSE-MIT"
    apache_license = root / "LICENSE-APACHE"
    root_license = root / "LICENSE"
    coc = root / "CODE_OF_CONDUCT.md"

    assert mit_license.is_file(), "Missing LICENSE-MIT"
    assert apache_license.is_file(), "Missing LICENSE-APACHE"
    assert root_license.is_file(), "Missing root LICENSE"
    assert coc.is_file(), "Missing CODE_OF_CONDUCT.md"

    mit_text = mit_license.read_text(encoding="utf-8")
    apache_text = apache_license.read_text(encoding="utf-8")
    root_text = root_license.read_text(encoding="utf-8")
    coc_text = coc.read_text(encoding="utf-8")

    assert "MIT License" in mit_text
    assert "Apache License" in apache_text
    assert "Version 2.0" in apache_text
    assert "dual-licensed" in root_text.lower()
    assert "Contributor Covenant" in coc_text


def test_pyproject_dual_license_declaration() -> None:
    root = Path(__file__).resolve().parent.parent
    pyproject_path = root / "pyproject.toml"
    assert pyproject_path.is_file()

    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)

    project_meta = data.get("project", {})
    license_declared = project_meta.get("license")
    assert license_declared == "MIT OR Apache-2.0", f"Unexpected license: {license_declared}"

    classifiers = project_meta.get("classifiers", [])
    assert "License :: OSI Approved :: MIT License" in classifiers
    assert "License :: OSI Approved :: Apache Software License" in classifiers
    for py_ver in ["3.11", "3.12", "3.13", "3.14", "3.15"]:
        assert f"Programming Language :: Python :: {py_ver}" in classifiers
