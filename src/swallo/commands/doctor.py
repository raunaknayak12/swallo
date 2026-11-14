"""
Implementation of the 'swallo doctor' diagnostics command.

Per TRD.md section 5, IMPLEMENTATION_PLAN.md Step 4, and ADR-020:
- Verifies store directory, permissions, and git worktree isolation.
- Verifies local cryptographic key file presence, length, and readability.
- Verifies SQLite database existence, connectivity, and applied schema migrations.
- Traverses and cryptographically verifies the tamper-evident event log.
- Inspects registered project roots.
- Verifies controlling terminal accessibility.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from swallo.config import (
    get_store_dir,
    is_inside_git_worktree,
    load_config,
)
from swallo.store.db import get_connection, get_schema_version
from swallo.store.eventlog import verify as verify_eventlog
from swallo.store.registry import list_projects
from swallo.terminal import is_terminal_available


def run_doctor(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="swallo doctor",
        description="Run security, configuration, and storage health diagnostics.",
    )
    parser.add_argument(
        "--store",
        type=Path,
        default=None,
        help="Custom store directory override.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON report.",
    )

    args = parser.parse_args(argv)

    store_dir = (args.store or get_store_dir()).resolve()
    key_path = store_dir / "key"
    config_path = store_dir / "config.toml"
    db_path = store_dir / "swallo.db"

    checks: list[dict[str, Any]] = []
    overall_ok = True

    # 1. Store Directory Check
    if not store_dir.exists():
        checks.append(
            {
                "name": "store_directory",
                "status": "FAIL",
                "detail": f"Store directory '{store_dir}' does not exist. Run 'swallo init'.",
            }
        )
        overall_ok = False
    else:
        in_git = is_inside_git_worktree(store_dir)
        if in_git:
            checks.append(
                {
                    "name": "store_directory",
                    "status": "WARN",
                    "detail": f"Store '{store_dir}' is inside a git repository work tree.",
                }
            )
        else:
            checks.append(
                {
                    "name": "store_directory",
                    "status": "OK",
                    "detail": f"Store exists at '{store_dir}' outside git work tree.",
                }
            )

    # 2. Key File Check
    key_bytes: bytes | None = None
    if not key_path.exists():
        checks.append(
            {
                "name": "key_file",
                "status": "FAIL",
                "detail": f"Key file '{key_path}' does not exist.",
            }
        )
        overall_ok = False
    else:
        try:
            key_bytes = key_path.read_bytes()
            if len(key_bytes) != 32:
                checks.append(
                    {
                        "name": "key_file",
                        "status": "FAIL",
                        "detail": f"Key file length is {len(key_bytes)} bytes; expected 32.",
                    }
                )
                overall_ok = False
            else:
                checks.append(
                    {
                        "name": "key_file",
                        "status": "OK",
                        "detail": f"Valid 32-byte cryptographic key at '{key_path}'.",
                    }
                )
        except Exception as e:
            checks.append(
                {
                    "name": "key_file",
                    "status": "FAIL",
                    "detail": f"Cannot read key file '{key_path}': {e}",
                }
            )
            overall_ok = False

    # 3. Config Check
    try:
        cfg, warnings = load_config(store_dir)
        if warnings:
            checks.append(
                {
                    "name": "config",
                    "status": "WARN",
                    "detail": f"Config loaded with warnings: {'; '.join(warnings)}",
                }
            )
        else:
            checks.append(
                {
                    "name": "config",
                    "status": "OK",
                    "detail": f"Config parsed successfully from '{config_path}'.",
                }
            )
    except Exception as e:
        checks.append(
            {
                "name": "config",
                "status": "FAIL",
                "detail": f"Config validation failed: {e}",
            }
        )
        overall_ok = False

    # 4. SQLite Database and Migrations Check
    projs: list[dict[str, Any]] = []
    if not db_path.exists():
        checks.append(
            {
                "name": "database",
                "status": "FAIL",
                "detail": f"Database file '{db_path}' does not exist.",
            }
        )
        overall_ok = False
    else:
        try:
            conn = get_connection(db_path)
            schema_ver = get_schema_version(conn)
            if schema_ver < 1:
                checks.append(
                    {
                        "name": "database",
                        "status": "FAIL",
                        "detail": f"Database schema version is {schema_ver}; migrations needed.",
                    }
                )
                overall_ok = False
            else:
                checks.append(
                    {
                        "name": "database",
                        "status": "OK",
                        "detail": f"Connected to '{db_path}' (schema v{schema_ver}).",
                    }
                )

                # 5. Event Log Verification Check
                if key_bytes:
                    log_errors = verify_eventlog(conn, key_bytes)
                    if log_errors:
                        checks.append(
                            {
                                "name": "event_log_integrity",
                                "status": "FAIL",
                                "detail": (
                                    f"Event log tampering detected: {len(log_errors)} error(s)."
                                ),
                            }
                        )
                        overall_ok = False
                    else:
                        checks.append(
                            {
                                "name": "event_log_integrity",
                                "status": "OK",
                                "detail": (
                                    "Event log hash chain verified successfully with zero errors."
                                ),
                            }
                        )

                # 6. Registered Projects Check
                projs = list_projects(conn)
                checks.append(
                    {
                        "name": "registered_projects",
                        "status": "OK",
                        "detail": f"{len(projs)} workspace root(s) registered.",
                    }
                )

        except Exception as e:
            checks.append(
                {
                    "name": "database",
                    "status": "FAIL",
                    "detail": f"Database error: {e}",
                }
            )
            overall_ok = False

    # 7. Terminal Check
    term_ok = is_terminal_available()
    checks.append(
        {
            "name": "terminal_access",
            "status": "OK" if term_ok else "INFO",
            "detail": (
                "Interactive terminal available for human approval"
                if term_ok
                else "Non-interactive / piped environment (commands requiring "
                "confirmation require an interactive TTY)"
            ),
        }
    )

    # 8. Workspace-level MCP Configuration Check (ADR-029, F20)
    cwd = Path.cwd().resolve()
    mcp_config_candidates = [
        cwd / ".vscode" / "mcp.json",
        cwd / ".cursor" / "mcp.json",
        cwd / "mcp.json",
    ]
    workspace_mcp_warns: list[str] = []
    for cand_file in mcp_config_candidates:
        if cand_file.is_file():
            try:
                cand_content = cand_file.read_text(encoding="utf-8", errors="ignore")
                if "swallo" in cand_content.lower():
                    workspace_mcp_warns.append(str(cand_file.relative_to(cwd)))
            except (OSError, PermissionError):
                # Ignore unreadable workspace config files
                pass

    if workspace_mcp_warns:
        warn_str = ", ".join(workspace_mcp_warns)
        checks.append(
            {
                "name": "mcp_workspace_config",
                "status": "WARN",
                "detail": (
                    f"Workspace-level MCP config found referencing swallo ({warn_str}). "
                    "Configure swallo MCP globally in user settings."
                ),
            }
        )
    else:
        checks.append(
            {
                "name": "mcp_workspace_config",
                "status": "OK",
                "detail": "No untrusted workspace-level MCP configurations detected.",
            }
        )

    # 9. Workspace Root Registration Check
    cwd_registered = any(
        Path(p["root_path"]).resolve() == cwd for p in projs
    )
    if not cwd_registered:
        checks.append(
            {
                "name": "workspace_root_registration",
                "status": "WARN",
                "detail": f"Current workspace root '{cwd}' is not registered with swallo.",
            }
        )
    else:
        checks.append(
            {
                "name": "workspace_root_registration",
                "status": "OK",
                "detail": f"Current workspace root '{cwd}' is registered.",
            }
        )

    # 10. Rogue Handoff Files Check
    handoff_dir = cwd / ".swallo" / "handoff"
    rogue_files: list[str] = []
    if handoff_dir.is_dir():
        try:
            for f in handoff_dir.iterdir():
                if f.is_file():
                    rogue_files.append(f.name)
        except (OSError, PermissionError):
            # Ignore inaccessible files in handoff dir
            pass

    if rogue_files:
        checks.append(
            {
                "name": "rogue_handoff_files",
                "status": "WARN",
                "detail": (
                    f"Found {len(rogue_files)} file(s) in .swallo/handoff/. "
                    "Verify ledger approvals to prevent unauthorized handoffs."
                ),
            }
        )
    else:
        checks.append(
            {
                "name": "rogue_handoff_files",
                "status": "OK",
                "detail": "No unverified handoff files found in workspace.",
            }
        )

    report = {
        "status": "OK" if overall_ok else "FAIL",
        "store_dir": str(store_dir),
        "checks": checks,
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"=== Swallo Doctor Diagnostic Report ({store_dir}) ===")
        for c in checks:
            badge = f"[{c['status']}]"
            print(f"  {badge:7} {c['name']}: {c['detail']}")
        print("=========================================================")
        if overall_ok:
            print("Status: All critical health and integrity checks passed.")
        else:
            print("Status: Issues detected. See failed checks above.", file=sys.stderr)

    return 0 if overall_ok else 1
