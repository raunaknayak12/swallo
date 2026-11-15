"""Stress test entire deterministic benchmark suite for 200 iterations."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is in sys.path
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from benchmarks.deterministic.runner import run_deterministic_suite  # noqa: E402
from swallo.bench.verify import verify_bench_results  # noqa: E402


def main() -> int:
    iterations = 200
    failures = 0
    print(f"Starting {iterations} iterations of run_deterministic_suite...")
    for i in range(1, iterations + 1):
        temp_out = repo_root / "benchmarks" / "results" / f"stress_deterministic_{i % 5}.json"
        data = run_deterministic_suite(out_path=temp_out)
        if not data.get("deterministic_summary", {}).get("all_defenses_passed", False):
            print(f"FAILED on iteration {i}: defenses did not all pass")
            failures += 1

        is_valid, logs = verify_bench_results(temp_out)
        if not is_valid:
            print(f"FAILED verify on iteration {i}: {logs}")
            failures += 1

        if i % 50 == 0:
            print(f"Progress: {i}/{iterations} iterations completed.")

    print(f"Completed {iterations} iterations. Total failures: {failures}")
    if failures > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
