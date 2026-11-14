#!/usr/bin/env python3
"""
Generate docs/CLI_REFERENCE.md from --help output of each swallo command.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

COMMANDS = [
    "init",
    "prompt",
    "save",
    "status",
    "list",
    "show",
    "approve",
    "send",
    "load",
    "diff",
    "merge",
    "resolve",
    "staleness",
    "drafts",
    "breaker",
    "import",
    "mcp",
    "bench",
    "doctor",
    "log",
    "version",
]


def generate_cli_reference() -> str:
    lines = [
        "# Swallo CLI Reference",
        "",
        "Auto-generated reference documentation from `swallo <command> --help`.",
        "",
    ]

    for cmd in COMMANDS:
        proc = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "swallo", cmd, "--help"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        help_text = (proc.stdout or proc.stderr).strip()
        lines.append(f"## `swallo {cmd}`")
        lines.append("")
        lines.append("```")
        lines.append(help_text)
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    docs_dir = Path(__file__).resolve().parents[1] / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    out_file = docs_dir / "CLI_REFERENCE.md"

    content = generate_cli_reference()

    if "--check" in sys.argv:
        if not out_file.exists():
            print(f"Error: {out_file} does not exist.", file=sys.stderr)
            return 1
        existing = out_file.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
        current = content.replace("\r\n", "\n").strip()
        if existing != current:
            print(
                f"Error: {out_file} has drifted from CLI --help. Run 'python scripts/gen_cli_docs.py' to update.",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {out_file} is in sync with CLI --help.")
        return 0

    out_file.write_text(content, encoding="utf-8")
    print(f"Generated {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
