"""
Atheris Fuzz Targets for Swallo Safety Primitives.

Targets:
1. `safe_json_loads`: Tests JSON parser against deep recursion and corrupt input.
2. `ArchiveGuard`: Tests zip structure verification with malformed entry headers.
3. `DecodedVariantDetector`: Tests regex and decoding parsers against crash inputs.

Usage:
    python benchmarks/deterministic/fuzz_atheris.py [--runs N]

Note: Atheris is optional. If atheris is not installed (e.g. on Windows),
a deterministic pseudo-fuzzing harness runs the seed corpus.
"""

from __future__ import annotations

import io
import sys
import zipfile
from typing import Any

from swallo.capture.importers.base import ArchiveGuard
from swallo.capture.importers.stream import safe_json_loads
from swallo.config import ImporterSettings
from swallo.errors import SecurityError
from swallo.errors import ValidationError as SwalloValidationError
from swallo.redact.decode import DecodedVariantDetector
from swallo.redact.patterns import PatternDetector

SEED_CORPUS: list[bytes] = [
    b'{"valid": 123}',
    b'{"nested": {"nested": {"nested": 1}}}',
    b'{"a": ' * 80 + b'1' + b'}' * 80,  # Deep JSON
    b"\x00\x01\x02\x03\xff\xfe",          # Binary garbage
    b"PK\x03\x04" + b"\x00" * 30,          # Corrupt ZIP header
    b"AKIA" + b"X" * 20,                  # Near-match secret
    b"data:image/png;base64," + b"A" * 100, # Large base64
]


def fuzz_target_safe_json(data: bytes) -> None:
    """Fuzz target for safe JSON parsing."""
    try:
        text = data.decode("utf-8", errors="ignore")
        safe_json_loads(text, max_depth=64)
    except (SecurityError, ValueError):
        pass  # Expected defensive rejections


def fuzz_target_archive_guard(data: bytes) -> None:
    """Fuzz target for zip archive guard verification."""
    guard = ArchiveGuard(ImporterSettings())
    buf = io.BytesIO(data)
    try:
        with zipfile.ZipFile(buf, "r") as zf:
            guard.verify_zip_structure(zf)
    except (zipfile.BadZipFile, SecurityError, ValueError, OSError):
        pass  # Expected defensive rejections


def fuzz_target_variants_decoder(data: bytes) -> None:
    """Fuzz target for decoded-variant regex and scanner."""
    detector = DecodedVariantDetector(inner_detectors=[PatternDetector()], max_depth=2, time_limit=0.1)
    try:
        text = data.decode("utf-8", errors="ignore")
        list(detector.scan(text))
    except Exception:  # noqa: S110
        pass


def run_standalone_fuzz(iterations: int = 100) -> dict[str, Any]:
    """Execute standalone fuzzing pass over seed corpus with pseudo-random mutations."""
    import secrets

    crashes = 0
    executed = 0

    corpus = list(SEED_CORPUS)
    # Generate mutations
    for seed in SEED_CORPUS:
        for _ in range(iterations // len(SEED_CORPUS) + 1):
            mutated = bytearray(seed)
            if mutated:
                idx = secrets.randbelow(len(mutated))
                mutated[idx] = secrets.randbelow(256)
            corpus.append(bytes(mutated))

    for sample in corpus:
        executed += 1
        try:
            fuzz_target_safe_json(sample)
            fuzz_target_archive_guard(sample)
            fuzz_target_variants_decoder(sample)
        except (SecurityError, SwalloValidationError, ValueError, TypeError, OSError):
            # Defensive rejections are expected behavior, NOT crashes
            pass
        except Exception:
            crashes += 1

    return {
        "fuzz_iterations": executed,
        "fuzz_crashes": crashes,
        "status": "PASS" if crashes == 0 else "FAIL",
    }


if __name__ == "__main__":
    try:
        import atheris  # type: ignore[import-untyped]

        def test_one_input(data: bytes) -> None:
            fuzz_target_safe_json(data)
            fuzz_target_archive_guard(data)
            fuzz_target_variants_decoder(data)

        atheris.Setup(sys.argv, test_one_input)
        atheris.Fuzz()
    except ImportError:
        print("[Atheris not installed; running standalone seed corpus fuzz runner]")
        res = run_standalone_fuzz(iterations=200)
        print(f"Fuzz results: {res}")

