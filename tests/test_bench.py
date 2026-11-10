"""
Unit and integration tests for the benchmark harness.

Covers:
- Fixture generation determinism and manifest hashing.
- Phase 1 metric computations.
- Schema serialization and roundtrip deserialization.
- 'swallo bench run' and 'swallo bench verify' CLI workflows.
- Tamper detection and error handling.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swallo.bench.fixtures import (
    build_fixture_set,
    fixture_manifest_sha256,
)
from swallo.bench.manifest import build_manifest, verify_manifest
from swallo.bench.metrics import run_phase1_benchmarks
from swallo.bench.runner import run_bench_cli
from swallo.bench.schema import (
    BenchEnvironment,
    BenchFixtureMeta,
    BenchResultEntry,
    BenchResults,
)
from swallo.bench.verify import verify_bench_cli, verify_bench_results
from swallo.cli import main


def test_fixtures_reproducibility() -> None:
    f1 = build_fixture_set(seed=42, count=10)
    f2 = build_fixture_set(seed=42, count=10)
    assert len(f1) == 10
    assert len(f2) == 10

    sha1 = fixture_manifest_sha256(f1)
    sha2 = fixture_manifest_sha256(f2)
    assert sha1 == sha2


def test_fixtures_different_seeds() -> None:
    f1 = build_fixture_set(seed=1, count=10)
    f2 = build_fixture_set(seed=2, count=10)
    sha1 = fixture_manifest_sha256(f1)
    sha2 = fixture_manifest_sha256(f2)
    assert sha1 != sha2


def test_manifest_verification() -> None:
    manifest = build_manifest(seed=999, count=20)
    assert verify_manifest(manifest) is True

    # Tampered manifest
    from dataclasses import replace

    tampered = replace(manifest, sha256="deadbeef" * 8)
    assert verify_manifest(tampered) is False


def test_phase1_metrics_computation() -> None:
    fixtures = build_fixture_set(seed=1234, count=15, secret_fraction=0.4)
    results = run_phase1_benchmarks(fixtures)

    names = [r.test for r in results]
    assert "secret_redaction_recall" in names
    assert "secret_redaction_precision" in names
    assert "latency_p50_ms" in names
    assert "latency_p95_ms" in names
    assert "determinism_score" in names
    assert "guard_behavior" in names

    det = next(r for r in results if r.test == "determinism_score")
    assert det.value == 1.0

    guard = next(r for r in results if r.test == "guard_behavior")
    assert guard.value == 1.0


def test_bench_results_roundtrip() -> None:
    results_obj = BenchResults(
        tool_version="0.1.0",
        schema_version="0.1",
        git_commit="abcdef123456",
        seed=42,
        environment=BenchEnvironment(os="TestOS", python="3.12.0", cpu="x86_64", memory_gb=16.0),
        fixtures=BenchFixtureMeta(manifest_sha256="abc123", count=10, split="dev"),
        results=[
            BenchResultEntry(test="determinism_score", n=10, value=1.0, ci=[1.0, 1.0]),
        ],
        logs="raw/",
    )
    json_str = results_obj.to_json()
    decoded_dict = json.JSONDecoder().decode(json_str)
    assert isinstance(decoded_dict, dict)

    reconstructed = BenchResults.from_dict(decoded_dict)
    assert reconstructed.tool_version == "0.1.0"
    assert reconstructed.schema_version == "0.1"
    assert reconstructed.git_commit == "abcdef123456"
    assert reconstructed.seed == 42
    assert reconstructed.fixtures.count == 10
    assert len(reconstructed.results) == 1
    assert reconstructed.results[0].test == "determinism_score"


def test_bench_run_and_verify_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out_file = tmp_path / "results.json"
    rc_run = run_bench_cli(["--count", "5", "--seed", "1234", "--out", str(out_file), "--json"])
    assert rc_run == 0
    assert out_file.is_file()
    capsys.readouterr()  # Clear stdout from runner

    # Verify run
    is_valid, logs = verify_bench_results(out_file)
    assert is_valid is True
    assert any("Fixture manifest integrity verified" in line for line in logs)

    rc_verify = verify_bench_cli([str(out_file), "--json"])
    assert rc_verify == 0
    captured = capsys.readouterr()
    report = json.JSONDecoder().decode(captured.out)
    assert isinstance(report, dict)
    assert report.get("valid") is True


def test_bench_verify_tamper_detection(tmp_path: Path) -> None:
    out_file = tmp_path / "tampered.json"
    run_bench_cli(["--count", "5", "--seed", "1234", "--out", str(out_file)])

    # 1. Tamper with fixture count
    raw = json.JSONDecoder().decode(out_file.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    fixtures_dict = raw.get("fixtures")
    assert isinstance(fixtures_dict, dict)
    fixtures_dict["count"] = 99
    out_file.write_text(json.dumps(raw), encoding="utf-8")

    is_valid, logs = verify_bench_results(out_file)
    assert is_valid is False
    assert any("Manifest SHA-256 mismatch" in line for line in logs)

    # 2. Tamper with schema_version
    raw["fixtures"]["count"] = 5
    raw["schema_version"] = "9.9"
    out_file.write_text(json.dumps(raw), encoding="utf-8")

    is_valid2, logs2 = verify_bench_results(out_file)
    assert is_valid2 is False
    assert any("Unsupported schema_version" in line for line in logs2)


def test_cli_bench_subcommand_dispatch(tmp_path: Path) -> None:
    # 1. swallo bench (help)
    assert main(["bench"]) == 0
    assert main(["bench", "--help"]) == 0

    # 2. swallo bench run
    res_path = tmp_path / "cli_results.json"
    assert main(["bench", "run", "--count", "4", "--out", str(res_path)]) == 0
    assert res_path.is_file()

    # 3. swallo bench verify
    assert main(["bench", "verify", str(res_path)]) == 0

    # 4. Unknown bench action
    assert main(["bench", "unknown_action"]) == 2
