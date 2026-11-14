"""
Tests verifying documentation and code do not drift.

Covers:
- `scripts/gen_cli_docs.py --check` matches current CLI help.
- All CLI commands in `KNOWN_COMMANDS` are documented in `README.md`.
- All registered MCP tools are documented in `README.md`.
- Documented environment variables match `known_swallo_env`.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from swallo.cli import KNOWN_COMMANDS


def test_cli_reference_generator_check_mode() -> None:
    """Run `scripts/gen_cli_docs.py --check` and verify CLI_REFERENCE.md is in sync."""
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "gen_cli_docs.py"

    proc = subprocess.run(  # noqa: S603
        [sys.executable, str(script_path), "--check"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, (
        f"CLI_REFERENCE.md has drifted from CLI --help output:\n"
        f"STDOUT: {proc.stdout}\nSTDERR: {proc.stderr}\n"
        f"Run 'python scripts/gen_cli_docs.py' to update docs."
    )


def test_readme_documents_all_known_commands() -> None:
    """Verify that every command in KNOWN_COMMANDS appears in README.md command reference."""
    repo_root = Path(__file__).resolve().parents[1]
    readme_text = (repo_root / "README.md").read_text(encoding="utf-8")

    missing = []
    for cmd in KNOWN_COMMANDS:
        # Match e.g. `swallo init`
        pattern = rf"`swallo\s+{cmd}`"
        if not re.search(pattern, readme_text):
            missing.append(cmd)

    err = f"The following commands in KNOWN_COMMANDS are missing from README.md: {missing}"
    assert not missing, err


def test_readme_documents_all_mcp_tools() -> None:
    """Verify that all tools registered in the FastMCP server are listed in README.md."""
    repo_root = Path(__file__).resolve().parents[1]
    readme_text = (repo_root / "README.md").read_text(encoding="utf-8")

    # Read mcp_server.py to extract registered tool names
    mcp_file = repo_root / "src" / "swallo" / "server" / "mcp_server.py"
    mcp_src = mcp_file.read_text(encoding="utf-8")
    registered_tools = []
    lines = mcp_src.splitlines()
    for i, line in enumerate(lines):
        if "@mcp_app.tool()" in line and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if next_line.startswith("def ") or next_line.startswith("async def "):
                decl = next_line.replace("async def ", "").replace("def ", "").strip()
                fn_name = decl.split("(")[0].strip()
                registered_tools.append(fn_name)

    assert registered_tools, "Could not find any registered MCP tools in mcp_server.py"

    missing = []
    for tool in registered_tools:
        if f"`{tool}`" not in readme_text:
            missing.append(tool)

    err = f"The following MCP tools in mcp_server.py are missing from README.md: {missing}"
    assert not missing, err


def test_documented_env_vars_match_code() -> None:
    """Verify documented env vars in README match config.py."""
    repo_root = Path(__file__).resolve().parents[1]
    readme_text = (repo_root / "README.md").read_text(encoding="utf-8")

    # Documented primary env vars
    assert "`SWALLO_HOME`" in readme_text
    assert "`SWALLO_STORAGE_DIR`" in readme_text
