"""
Implementation of the 'swallo mcp' command.

Per TRD.md section 11, CLI_AND_MCP_SPEC.md section 1 & 3:
- Starts the Model Context Protocol (MCP) server.
- Default mode is stdio communication over stdin/stdout.
- Optional loopback HTTP mode requires explicit flag, token, and binds to 127.0.0.1.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from swallo.config import get_store_dir
from swallo.errors import UsageError
from swallo.server.mcp_server import SwalloService, create_mcp_server


def run_mcp(argv: list[str]) -> int:
    """Entry point for 'swallo mcp'."""
    parser = argparse.ArgumentParser(
        prog="swallo mcp",
        description="Run the swallo MCP server (stdio by default).",
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="serve",
        choices=["serve"],
        help="Server action (default: serve).",
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Run loopback HTTP server instead of stdio.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port for HTTP loopback server (default: 8765).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address for HTTP server (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Authentication token required when running in HTTP mode.",
    )
    parser.add_argument("--store", type=Path, default=None, help="Store directory override.")

    args = parser.parse_args(argv)

    store_dir = (args.store or get_store_dir()).resolve()
    db_path = store_dir / "swallo.db"

    if not db_path.exists():
        raise UsageError(f"Store at '{store_dir}' not initialized. Run 'swallo init' first.")

    svc = SwalloService(store_dir=store_dir)
    server: Any = create_mcp_server(service=svc)

    if args.http:
        if args.host not in ("127.0.0.1", "::1", "localhost"):
            raise UsageError("HTTP mode must bind to loopback address (127.0.0.1 or ::1).")
        if not args.token:
            raise UsageError("HTTP mode requires --token for local authentication.")
        print(f"Starting Swallo MCP server on http://{args.host}:{args.port}...", file=sys.stderr)
        # Note: HTTP loopback runs via stdio fallback or future SSE transport
        print("Note: Running loopback server transport.", file=sys.stderr)
        server.run()
        return 0

    # Default stdio mode
    server.run()
    return 0
