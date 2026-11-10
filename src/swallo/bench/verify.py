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


def _verify_deterministic_bench_results(
    raw_obj: dict[str, object],
) -> tuple[bool, list[str]]:
    """
    Verify deterministic correctness benchmark results.
    Compares metrics only and ignores environment fields (git SHA, OS, Python version, timestamps).
    """
    logs: list[str] = []

    # 1. Schema version
    schema_ver = raw_obj.get("schema_version")
    if schema_ver != "0.1":
        logs.append(f"FAIL: Unsupported schema_version '{schema_ver}'. Expected '0.1'.")
        return False, logs
    logs.append("PASS: Schema version is '0.1'.")

    # 2. Metrics check
    metrics = raw_obj.get("metrics")
    if not isinstance(metrics, dict):
        logs.append("FAIL: Missing or invalid 'metrics' mapping.")
        return False, logs

    summary = raw_obj.get("deterministic_summary")
    if not isinstance(summary, dict):
        logs.append("FAIL: Missing or invalid 'deterministic_summary' mapping.")
        return False, logs

    # Required deterministic metric areas
    required_areas = [
        "corpus_redaction",
        "decoded_variants",
        "hash_stability",
        "defense_matrix",
        "sanitizer",
        "tamper_detection",
        "security_invariants",
    ]
    missing = [a for a in required_areas if a not in metrics]
    if missing:
        logs.append(f"FAIL: Missing required deterministic benchmark areas: {', '.join(missing)}")
        return False, logs

    # Verify key invariant thresholds
    defense_matrix = metrics.get("defense_matrix", {})
    if isinstance(defense_matrix, dict) and defense_matrix.get("defense_matrix_pass_rate") != 1.0:
        logs.append("FAIL: Defense matrix pass rate is not 100%.")
        return False, logs
    logs.append("PASS: Defense matrix pass rate: 100%")

    sanitizer = metrics.get("sanitizer", {})
    if isinstance(sanitizer, dict) and sanitizer.get("sanitizer_overall_pass_rate") != 1.0:
        logs.append("FAIL: Sanitizer pass rate is not 100%.")
        return False, logs
    logs.append("PASS: Sanitizer pass rate: 100%")

    tamper = metrics.get("tamper_detection", {})
    if isinstance(tamper, dict) and tamper.get("overall_tamper_detection_rate") != 1.0:
        logs.append("FAIL: Tamper detection rate is not 100%.")
        return False, logs
    logs.append("PASS: Tamper detection rate: 100%")

    invariants = metrics.get("security_invariants", {})
    if isinstance(invariants, dict) and not invariants.get("all_invariants_hold"):
        logs.append("FAIL: Security invariants failed.")
        return False, logs
    logs.append("PASS: Security invariants: All invariants hold")

    redaction = metrics.get("corpus_redaction", {})
    if isinstance(redaction, dict):
        f1 = redaction.get("pattern_f1", 0.0)
        logs.append(f"PASS: Redaction pattern F1: {f1}")

    return True, logs


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

        # Check if this is the Phase 2 deterministic benchmark format
        # (benchmarks/results/deterministic.json)
        if "metrics" in raw_obj and "deterministic_summary" in raw_obj:
            return _verify_deterministic_bench_results(raw_obj)

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
