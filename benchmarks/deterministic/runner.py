"""
Deterministic Correctness Benchmark Suite Runner.

Executes all deterministic benchmarks without timing assertions:
1. Redaction accuracy & entropy detector evaluation (corpus.py)
2. Decoded-variant recall and decode-bomb caps (variants.py)
3. Canonical hash stability & float/int boundary checks (hash_stability.py)
4. Defense matrix pass/fail evaluation (defense_matrix.py)
5. Trojan Source sanitizer neutralization (sanitizer.py)
6. Tamper detection on eventlog & ledger (tamper_detection.py)
7. Security invariants verification (invariants.py)
8. Safety primitives fuzz check (fuzz_atheris.py)

Exports results to benchmarks/results/deterministic.json.
"""

from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path
from typing import Any

from benchmarks.deterministic.corpus import evaluate_corpus_redaction
from benchmarks.deterministic.defense_matrix import evaluate_defense_matrix
from benchmarks.deterministic.fuzz_atheris import run_standalone_fuzz
from benchmarks.deterministic.hash_stability import evaluate_hash_stability
from benchmarks.deterministic.invariants import evaluate_security_invariants
from benchmarks.deterministic.sanitizer import evaluate_sanitizer
from benchmarks.deterministic.tamper_detection import evaluate_tamper_detection
from benchmarks.deterministic.variants import evaluate_decoded_variants
from swallo import __version__


def _get_git_commit() -> str:
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
    except Exception:  # noqa: S110
        pass
    return "unknown"


def run_deterministic_suite(out_path: Path | None = None) -> dict[str, Any]:
    """Execute complete deterministic benchmark suite and export results."""
    print("Executing Deterministic Correctness Benchmark Suite...")

    # 1. Environment Metadata
    environment: dict[str, Any] = {
        "os": f"{platform.system()} {platform.release()}",
        "architecture": platform.architecture()[0],
        "python_version": platform.python_version(),
        "cpu": platform.processor() or platform.machine() or "unknown",
    }

    # 2. Execute Deterministic Benchmark Modules
    print("  -> Evaluating Secret Redaction Corpus...")
    corpus_results = evaluate_corpus_redaction()

    print("  -> Evaluating Decoded Variants & Decode-Bomb Caps...")
    variants_results = evaluate_decoded_variants()

    print("  -> Evaluating Canonical Hash Stability & Invariants...")
    hash_results = evaluate_hash_stability()

    print("  -> Evaluating Defense Matrix (Zip-Slip, Bombs, Traversal)...")
    defense_results = evaluate_defense_matrix()

    print("  -> Evaluating Trojan Source Sanitizer (CVE-2021-42574)...")
    sanitizer_results = evaluate_sanitizer()

    print("  -> Evaluating Event Log & Ledger Tamper Detection...")
    tamper_results = evaluate_tamper_detection()

    print("  -> Evaluating Security Invariants...")
    invariants_results = evaluate_security_invariants()

    print("  -> Evaluating Standalone Safety Fuzz Runner...")
    fuzz_results = run_standalone_fuzz(iterations=100)

    # 3. Assemble Output Document
    output: dict[str, Any] = {
        "schema_version": "0.1",
        "swallo_version": __version__,
        "git_commit": _get_git_commit(),
        "environment": environment,
        "metrics": {
            "corpus_redaction": corpus_results,
            "decoded_variants": variants_results,
            "hash_stability": hash_results,
            "defense_matrix": defense_results,
            "sanitizer": sanitizer_results,
            "tamper_detection": tamper_results,
            "security_invariants": invariants_results,
            "fuzz_testing": fuzz_results,
        },
        "deterministic_summary": {
            "all_defenses_passed": bool(
                defense_results.get("defense_matrix_pass_rate") == 1.0
                and sanitizer_results.get("sanitizer_overall_pass_rate") == 1.0
                and tamper_results.get("overall_tamper_detection_rate") == 1.0
                and invariants_results.get("all_invariants_hold") is True
            ),
            "redaction_f1": corpus_results.get("pattern_f1", 0.0),
            "variant_recall_base64": variants_results.get("base64_recall", 0.0),
            "variant_recall_rot13": variants_results.get("rot13_recall", 0.0),
            "variant_recall_reversal": variants_results.get("reversal_recall", 0.0),
            "variant_recall_zero_width": variants_results.get("zero_width_recall", 0.0),
            "tamper_detection_rate": tamper_results.get("overall_tamper_detection_rate", 0.0),
        },
    }

    # 4. Save to Disk
    if out_path is None:
        out_path = Path("benchmarks/results/deterministic.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Results successfully written to: {out_path}")
    return output


if __name__ == "__main__":
    run_deterministic_suite()

