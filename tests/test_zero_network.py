"""
Zero-network AST regression test suite.

Inspects all source Python ASTs in src/swallo to guarantee that no networking
libraries (urllib, urllib.request, requests, httpx, aiohttp, socket, websocket)
are imported in core modules.
"""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_MODULES = {
    "urllib.request",
    "requests",
    "httpx",
    "aiohttp",
    "socket",
    "websocket",
    "websockets",
    "http.client",
}


def _check_file_imports(path: Path) -> list[str]:
    content = path.read_text(encoding="utf-8")
    tree = ast.parse(content, filename=str(path))
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for forbidden in FORBIDDEN_MODULES:
                    if alias.name == forbidden or alias.name.startswith(f"{forbidden}."):
                        violations.append(f"{path}:{node.lineno} imports '{alias.name}'")
        elif isinstance(node, ast.ImportFrom) and node.module:
            for forbidden in FORBIDDEN_MODULES:
                if node.module == forbidden or node.module.startswith(f"{forbidden}."):
                    violations.append(f"{path}:{node.lineno} imports from '{node.module}'")

    return violations


def test_zero_network_ast_scan() -> None:
    src_dir = Path(__file__).resolve().parents[1] / "src" / "swallo"
    assert src_dir.is_dir(), f"Source directory not found: {src_dir}"

    all_violations: list[str] = []
    for py_file in src_dir.rglob("*.py"):
        violations = _check_file_imports(py_file)
        all_violations.extend(violations)

    assert not all_violations, (
        "Zero-network invariant violated! The following network imports were detected:\n"
        + "\n".join(all_violations)
    )
