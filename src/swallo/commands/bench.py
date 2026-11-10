"""
Implementation of 'swallo bench' command.

Per BENCHMARKS.md and COMMANDS.md:
- Subcommands:
  - swallo bench run [--phase N] [--seed S] [--out FILE]
  - swallo bench verify RESULTS.json
"""

from __future__ import annotations

import sys

from swallo.errors import UsageError


def run_bench(argv: list[str]) -> int:
    """Entry point for 'swallo bench'."""
    if not argv or argv[0] in ("-h", "--help", "help"):
        print("Usage: swallo bench <action> [options]\n")
        print("Actions:")
        print("  run     Execute benchmark suite and output results.json")
        print("  verify  Validate schema and cryptographic integrity of results.json\n")
        print("Run 'swallo bench <action> --help' for details on a specific action.")
        return 0

    action = argv[0].lower()
    sub_args = argv[1:]

    if action == "run":
        from swallo.bench.runner import run_bench_cli

        return run_bench_cli(sub_args)

    if action == "verify":
        from swallo.bench.verify import verify_bench_cli

        return verify_bench_cli(sub_args)

    print(
        f"Error: Unknown bench action '{action}'. Supported actions: run, verify.",
        file=sys.stderr,
    )
    return UsageError.exit_code
