"""Stress test tamper detection benchmark for 500 iterations."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is in sys.path
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from benchmarks.deterministic.tamper_detection import evaluate_tamper_detection  # noqa: E402


def main() -> int:
    iterations = 500
    failures = 0
    print(f"Starting {iterations} iterations of evaluate_tamper_detection...")
    for i in range(1, iterations + 1):
        res = evaluate_tamper_detection()
        if res.get("overall_tamper_detection_rate") != 1.0:
            print(f"FAILED on iteration {i}: {res}")
            failures += 1
        if i % 100 == 0:
            print(f"Progress: {i}/{iterations} iterations completed.")

    print(f"Completed {iterations} iterations. Total failures: {failures}")
    if failures > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
