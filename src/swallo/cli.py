"""
Command line interface for swallo.
"""

from __future__ import annotations

import argparse
import difflib
import json
import platform
import sys

from swallo import __version__
from swallo.errors import UsageError

SUPPORTED_SCHEMA_VERSIONS = ["0.1"]
KNOWN_COMMANDS = [
    "help",
    "version",
    "init",
    "prompt",
    "save",
    "import",
    "merge",
    "resolve",
    "show",
    "edit",
    "approve",
    "send",
    "load",
    "diff",
    "list",
    "status",
    "log",
    "staleness",
    "drafts",
    "breaker",
    "bench",
    "doctor",
    "mcp",
]


def _build_version_dict() -> dict[str, object]:
    return {
        "version": __version__,
        "supported_schema_versions": list(SUPPORTED_SCHEMA_VERSIONS),
        "python_version": platform.python_version(),
    }


def _run_version(as_json: bool) -> int:
    data = _build_version_dict()
    if as_json:
        print(json.dumps(data, indent=2))
    else:
        print(f"swallo {data['version']}")
        print(f"supported schema versions: {', '.join(SUPPORTED_SCHEMA_VERSIONS)}")
        print(f"python: {data['python_version']} ({platform.architecture()[0]})")
    return 0


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    # Quick check for version flag
    if "--version" in argv or "-V" in argv:
        return _run_version(as_json="--json" in argv)

    parser = argparse.ArgumentParser(
        prog="swallo",
        description="Portable, reviewable handoff between any chat agent and any IDE.",
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="store_true", help="Show help overview and exit.")
    parser.add_argument("-V", "--version", action="store_true", help="Show version and exit.")
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output.")
    parser.add_argument("subcommand", nargs="?", help="Subcommand to execute.")
    parser.add_argument(
        "subcommand_args",
        nargs=argparse.REMAINDER,
        help="Arguments for subcommand.",
    )

    args, extra = parser.parse_known_args(argv)

    if args.version:
        return _run_version(as_json=args.json)

    if args.subcommand is None:
        if args.help:
            print("Usage: swallo <command> [options]\n")
            print("Commands:")
            for cmd in KNOWN_COMMANDS:
                print(f"  {cmd}")
            print("\nUse 'swallo help [command]' for more details.")
            return 0
        print(
            "Usage: swallo <command> [options]\nRun 'swallo help' or 'swallo --help' for details.",
            file=sys.stderr,
        )
        return 0

    subcommand = args.subcommand.lower()

    if subcommand == "version":
        as_json = args.json or ("--json" in (args.subcommand_args or []))
        return _run_version(as_json=as_json)

    if subcommand == "help":
        print("Usage: swallo <command> [options]\n")
        print("Available commands:")
        for cmd in sorted(KNOWN_COMMANDS):
            print(f"  {cmd}")
        return 0

    sub_args = list(args.subcommand_args or [])
    if args.json and "--json" not in sub_args:
        sub_args.append("--json")

    if subcommand == "init":
        from swallo.commands.init import run_init

        return run_init(sub_args)

    if subcommand == "prompt":
        from swallo.commands.prompt import run_prompt

        return run_prompt(sub_args)

    if subcommand == "doctor":
        from swallo.commands.doctor import run_doctor

        return run_doctor(sub_args)

    if subcommand == "save":
        from swallo.commands.save import run_save

        return run_save(sub_args)

    if subcommand == "import":
        from swallo.commands.import_cmd import run_import

        return run_import(sub_args)

    if subcommand == "show":
        from swallo.commands.show import run_show

        return run_show(sub_args)

    if subcommand == "approve":
        from swallo.commands.approve import run_approve

        return run_approve(sub_args)

    if subcommand == "log":
        from swallo.commands.log import run_log

        return run_log(sub_args)

    if subcommand == "send":
        from swallo.commands.send import run_send

        return run_send(sub_args)

    if subcommand == "load":
        from swallo.commands.load import run_load

        return run_load(sub_args)

    if subcommand == "merge":
        from swallo.commands.merge import run_merge

        return run_merge(sub_args)

    if subcommand == "resolve":
        from swallo.commands.resolve import run_resolve

        return run_resolve(sub_args)

    if subcommand == "diff":
        from swallo.commands.diff import run_diff

        return run_diff(sub_args)

    if subcommand == "staleness":
        from swallo.commands.staleness import run_staleness

        return run_staleness(sub_args)

    if subcommand == "breaker":
        from swallo.commands.breaker import run_breaker

        return run_breaker(sub_args)

    if subcommand == "drafts":
        from swallo.commands.drafts import run_drafts

        return run_drafts(sub_args)

    if subcommand in ("status", "list"):
        from swallo.commands.status import run_status

        return run_status(sub_args)

    if subcommand == "edit":
        from swallo.commands.edit import run_edit

        return run_edit(sub_args)

    if subcommand == "mcp":
        from swallo.commands.mcp import run_mcp

        return run_mcp(sub_args)

    if subcommand == "bench":
        from swallo.commands.bench import run_bench

        return run_bench(sub_args)

    # Unknown subcommand check with close-match suggestion
    if subcommand not in KNOWN_COMMANDS:
        suggestions = difflib.get_close_matches(subcommand, KNOWN_COMMANDS, n=3, cutoff=0.5)
        msg = f"Unknown command: '{subcommand}'."
        if suggestions:
            msg += f" Did you mean: {', '.join(suggestions)}?"
        print(f"Error: {msg}", file=sys.stderr)
        return UsageError.exit_code

    # For commands not yet implemented in Steps 0-2
    print(f"Command '{subcommand}' is planned but not implemented in this build.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
