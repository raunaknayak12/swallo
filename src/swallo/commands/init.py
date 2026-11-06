"""
Implementation of the 'swallo init' command.

Per TRD.md section 5, IMPLEMENTATION_PLAN.md Steps 2 and 4, and ADR-020:
- Creates the local store directory (%LOCALAPPDATA%/swallo or ~/.local/share/swallo).
- Generates the 32-byte cryptographic local key (0600 permissions).
- Writes default config.toml from the template if not already present.
- Initializes the SQLite database and applies schema migrations.
- Registers the current working directory / project root.
- Re-initializing an existing store requires --force (and logs store_reinit).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from swallo.config import (
    get_default_config_template,
    get_store_dir,
    is_inside_git_worktree,
)
from swallo.errors import UsageError
from swallo.store.db import apply_migrations, get_connection, get_or_create_local_key
from swallo.store.eventlog import append as log_event
from swallo.store.registry import register_project
from swallo.terminal import confirm_on_terminal


def run_init(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="swallo init",
        description="Initialize swallo storage, local key, database, and project registry.",
    )
    parser.add_argument(
        "--store",
        type=Path,
        default=None,
        help="Custom store directory override.",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force re-initialization of an existing store.",
    )
    parser.add_argument(
        "--project",
        "-p",
        type=str,
        default=None,
        help="Project name to register for the current directory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON.",
    )

    args = parser.parse_args(argv)

    store_dir = args.store or get_store_dir()
    store_dir = store_dir.resolve()
    key_path = store_dir / "key"
    config_path = store_dir / "config.toml"
    db_path = store_dir / "swallo.db"

    is_reinit = store_dir.exists() and key_path.exists()
    if is_reinit and not args.force:
        try:
            confirmed = confirm_on_terminal(
                f"Store at '{store_dir}' already exists. Overwrite/reinitialize?",
                default=False,
            )
        except UsageError:
            confirmed = False

        if not confirmed:
            msg = f"Store at '{store_dir}' already initialized. Use --force to re-initialize."
            if args.json:
                print(json.dumps({"error": msg, "status": "aborted"}))
            else:
                print(f"Error: {msg}", file=sys.stderr)
            return UsageError.exit_code

    # 1. Create store directory
    store_dir.mkdir(parents=True, exist_ok=True)

    # 2. Key generation
    key_bytes = get_or_create_local_key(key_path)

    # 3. Default config.toml
    if not config_path.exists():
        config_path.write_text(get_default_config_template(), encoding="utf-8")

    # 4. SQLite DB & migrations
    conn = get_connection(db_path)
    schema_ver = apply_migrations(conn)

    # 5. Log init event
    event_type = "store_reinit" if is_reinit else "store_init"
    log_event(
        conn,
        key_bytes,
        type=event_type,
        detail=f"Initialized store at {store_dir} with schema version {schema_ver}",
    )

    # 6. Register current directory
    cwd = Path.cwd().resolve()
    reg_info = register_project(conn, cwd, name=args.project)

    # 7. Check if inside git worktree and warn
    in_git = is_inside_git_worktree(store_dir)
    warnings: list[str] = []
    if in_git:
        warnings.append(
            f"Warning: Store directory '{store_dir}' is inside a git repository work tree. "
            "Sensitive data or keys may be accidentally tracked in version control."
        )

    # 8. MCP server snippet
    mcp_snippet = {
        "command": sys.executable,
        "args": ["-m", "swallo", "mcp", "serve"],
    }

    out_data = {
        "status": "initialized",
        "store_dir": str(store_dir),
        "key_file": str(key_path),
        "config_file": str(config_path),
        "db_file": str(db_path),
        "schema_version": schema_ver,
        "registered_project": reg_info,
        "mcp_config": mcp_snippet,
        "warnings": warnings,
    }

    if args.json:
        print(json.dumps(out_data, indent=2))
    else:
        print(f"Swallo storage successfully initialized at: {store_dir}")
        print(f"  Database: {db_path} (schema v{schema_ver})")
        print(f"  Key file: {key_path} (32 bytes local cryptographic key)")
        print(f"  Config:   {config_path}")
        print(f"  Project:  Registered '{reg_info['name']}' at {reg_info['root_path']}")
        print(f"  MCP Server Command: {sys.executable} -m swallo mcp serve")
        for w in warnings:
            print(w, file=sys.stderr)

    return 0
