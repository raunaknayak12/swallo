"""
Benchmark runner module for executing benchmark suites.

Per BENCHMARKS.md:
- Collects environment metadata (OS, Python version, CPU, memory).
- Generates reproducible fixtures using the specified seed.
- Computes Phase 1 metrics (redaction, latency, determinism, guard behavior).
- Produces and writes results.json conforming to schema_version 0.1.
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path

from swallo import __version__
from swallo.bench.fixtures import build_fixture_set, fixture_manifest_sha256
from swallo.bench.metrics import run_phase1_benchmarks
from swallo.bench.schema import BenchEnvironment, BenchFixtureMeta, BenchResults


def _get_git_commit() -> str:
    """Retrieve current git HEAD commit hash safely with a timeout."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S603, S607
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        pass
    return "unknown"


def _get_memory_gb() -> float:
    """Estimate total system memory in GB safely across platforms."""
    if sys.platform != "win32":
        return 0.0
    try:
        import ctypes

        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MemoryStatusEx()
        stat.dwLength = ctypes.sizeof(MemoryStatusEx)
        kernel32 = getattr(ctypes.windll, "kernel32", None)
        if kernel32 and kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return float(round(stat.ullTotalPhys / (1024**3), 2))
    except (AttributeError, OSError):
        return 0.0
    return 0.0


def _collect_environment() -> BenchEnvironment:
    """Snapshot runtime environment for benchmark metadata."""
    cpu = platform.processor() or platform.machine() or "unknown"
    return BenchEnvironment(
        os=f"{platform.system()} {platform.release()}",
        python=platform.python_version(),
        cpu=cpu,
        memory_gb=_get_memory_gb(),
    )


def run_bench_cli(argv: list[str]) -> int:
    """
    Execute benchmark suite and write results.json.

    Args:
        argv: Command-line arguments for 'bench run'.
    """
    parser = argparse.ArgumentParser(
        prog="swallo bench run",
        description="Run swallo benchmark suite and export results.json.",
    )
    parser.add_argument(
        "--phase",
        type=int,
        default=1,
        help="Benchmark phase to execute (default: 1).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=1234,
        help="Random seed for reproducible fixture generation (default: 1234).",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=50,
        help="Number of synthetic packet fixtures to generate (default: 50).",
    )
    parser.add_argument(
        "--split",
        type=str,
        default="dev",
        help="Dataset split identifier ('dev' or 'sealed').",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("bench_results.json"),
        help="Output path for benchmark results.json (default: bench_results.json).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw results.json to stdout.",
    )

    args = parser.parse_args(argv)

    if args.phase != 1:
        print(f"Error: Phase {args.phase} is not yet implemented. Supported: 1", file=sys.stderr)
        return 1

    # 1. Environment & Commit
    env = _collect_environment()
    commit = _get_git_commit()

    # 2. Build Fixtures & Manifest Hash
    fixtures = build_fixture_set(seed=args.seed, count=args.count)
    manifest_sha = fixture_manifest_sha256(fixtures)
    fixture_meta = BenchFixtureMeta(
        manifest_sha256=manifest_sha,
        count=args.count,
        split=args.split,
    )

    # 3. Compute Phase 1 metrics
    results = run_phase1_benchmarks(fixtures)

    # 4. Construct container
    bench_data = BenchResults(
        tool_version=__version__,
        schema_version="0.1",
        git_commit=commit,
        seed=args.seed,
        environment=env,
        fixtures=fixture_meta,
        results=results,
        logs="raw/",
    )

    # 5. Write to file
    out_path = args.out.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(bench_data.to_json(indent=2), encoding="utf-8")

    # 6. Display output
    if args.json:
        print(bench_data.to_json(indent=2))
    else:
        print(f"Benchmark Phase {args.phase} complete.")
        print(f"  Fixtures: {args.count} (seed: {args.seed}, SHA: {manifest_sha[:12]}...)")
        print(f"  Results saved to: {out_path}\n")
        print("Metrics Summary:")
        for r in results:
            print(f"  - {r.test:<28}: {r.value:>8.4f}  (n={r.n}, CI: {r.ci})")

    return 0
