"""
Benchmark verifier module for validating benchmark results.

Per BENCHMARKS.md:
- Reads results.json using safe JSON decoding.
- Re-generates fixtures from seed and re-computes manifest SHA-256.
- Detects tampered results or invalid schema versions.
- Validates required metrics and threshold adherence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from swallo.bench.fixtures import build_fixture_set, fixture_manifest_sha256
from swallo.bench.schema import BenchResults


def verify_bench_results(
    results_path: Path,
) -> tuple[bool, list[str]]:
    """
    Verify schema and cryptographic integrity of a benchmark results file.

    Args:
        results_path: Path to results.json.

    Returns:
        (is_valid, list_of_verification_logs)
    """
    logs: list[str] = []

    if not results_path.is_file():
        return False, [f"File not found: {results_path}"]

    try:
        content = results_path.read_text(encoding="utf-8")
        raw_obj = json.JSONDecoder().decode(content)
        if not isinstance(raw_obj, dict):
            return False, ["Invalid JSON: root must be an object."]
        data = BenchResults.from_dict(raw_obj)
    except Exception as exc:
        return False, [f"Failed to parse results.json: {exc}"]

    # 1. Schema version check
    if data.schema_version != "0.1":
        logs.append(
            f"FAIL: Unsupported schema_version '{data.schema_version}'. Expected '0.1'."
        )
        return False, logs
    logs.append("PASS: Schema version is '0.1'.")

    # 2. Tool version & git commit
    if not data.tool_version:
        logs.append("FAIL: Missing tool_version.")
        return False, logs
    logs.append(f"PASS: Tool version: {data.tool_version}")
    logs.append(f"PASS: Git commit: {data.git_commit[:12] if data.git_commit else 'unknown'}")

    # 3. Fixture manifest recomputation
    seed = data.seed
    count = data.fixtures.count
    expected_sha = data.fixtures.manifest_sha256

    if count <= 0:
        logs.append(f"FAIL: Fixture count must be positive, got {count}.")
        return False, logs

    fixtures = build_fixture_set(seed=seed, count=count)
    computed_sha = fixture_manifest_sha256(fixtures)

    if computed_sha != expected_sha:
        logs.append(
            f"FAIL: Manifest SHA-256 mismatch!\n"
            f"  Stored:   {expected_sha}\n"
            f"  Computed: {computed_sha}"
        )
        return False, logs
    logs.append(f"PASS: Fixture manifest integrity verified (SHA: {computed_sha[:12]}...).")

    # 4. Results check
    metric_names = {r.test: r.value for r in data.results}
    required_tests = ["secret_redaction_recall", "determinism_score", "guard_behavior"]
    missing = [t for t in required_tests if t not in metric_names]
    if missing:
        logs.append(f"FAIL: Missing required metrics: {', '.join(missing)}")
        return False, logs

    # Determinism threshold
    det = metric_names.get("determinism_score", 0.0)
    if det < 1.0:
        logs.append(f"FAIL: Determinism score is {det}, expected 1.0.")
        return False, logs
    logs.append(f"PASS: Determinism score: {det:.4f}")

    recall = metric_names.get("secret_redaction_recall", 0.0)
    logs.append(f"PASS: Secret redaction recall: {recall:.4f}")

    guard = metric_names.get("guard_behavior", 0.0)
    logs.append(f"PASS: Guard behavior: {guard:.4f}")

    return True, logs


def verify_bench_cli(argv: list[str]) -> int:
    """
    CLI command handler for 'swallo bench verify'.

    Args:
        argv: Command-line arguments.
    """
    parser = argparse.ArgumentParser(
        prog="swallo bench verify",
        description="Verify cryptographic integrity and schema of benchmark results.",
    )
    parser.add_argument(
        "results_path",
        type=Path,
        help="Path to results.json file to verify.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON verification report.",
    )

    args = parser.parse_args(argv)

    is_valid, logs = verify_bench_results(args.results_path)

    if args.json:
        report = {
            "valid": is_valid,
            "path": str(args.results_path),
            "logs": logs,
        }
        print(json.dumps(report, indent=2))
    else:
        for line in logs:
            print(line)
        status = "PASSED" if is_valid else "FAILED"
        print(f"\nVerification: {status}")

    return 0 if is_valid else 1
