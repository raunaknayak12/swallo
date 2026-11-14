"""
Separately runnable Atheris fuzz targets for Swallo security-critical parsers.

Targets:
1. safe_json_loads (deep recursion, invalid structures, malformed control codes)
2. DecodedVariantDetector (variant expansions, malformed encodings, ReDoS payloads)
3. ArchiveGuard.verify_zip_structure (zip bombs, zip-slip, entry overflows)

Run manually in Linux fuzzing container:
    python tests/fuzz_atheris.py
"""

from __future__ import annotations

import io
import logging
import sys
import zipfile

from swallo.capture.importers.base import ArchiveGuard
from swallo.capture.importers.stream import safe_json_loads
from swallo.config import ImporterSettings
from swallo.errors import SecurityError, ValidationError
from swallo.redact.decode import DecodedVariantDetector
from swallo.redact.patterns import PatternDetector

logger = logging.getLogger(__name__)

try:
    import atheris
except ImportError:
    atheris = None  # type: ignore[assignment]


def fuzz_safe_json(data: bytes) -> None:
    """Fuzz target for safe JSON parsing."""
    try:
        text = data.decode("utf-8", errors="ignore")
    except Exception:
        return

    try:
        safe_json_loads(text, max_depth=50)
    except (SecurityError, ValidationError):
        pass  # Expected safe rejection


def fuzz_variant_detector(data: bytes) -> None:
    """Fuzz target for decoded variant detector."""
    try:
        text = data.decode("utf-8", errors="ignore")
    except Exception:
        return

    detector = DecodedVariantDetector(inner_detectors=[PatternDetector()], time_limit=0.1)
    try:
        list(detector.scan(text))
    except (ValueError, UnicodeDecodeError, SecurityError, ValidationError) as exc:
        logger.debug("Expected rejection in fuzz_variant_detector: %s", exc)


def fuzz_zip_guard(data: bytes) -> None:
    """Fuzz target for zip archive guard."""
    guard = ArchiveGuard(ImporterSettings(max_entries=100, max_archive_bytes=1024 * 1024))
    buf = io.BytesIO(data)
    try:
        if zipfile.is_zipfile(buf):
            with zipfile.ZipFile(buf, "r") as zf:
                guard.verify_zip_structure(zf)
    except (SecurityError, ValidationError, zipfile.BadZipFile):
        pass


def test_atheris_fuzz_harness_smoke() -> None:
    """Smoke test ensuring fuzz functions handle synthetic inputs without unhandled crashes."""
    # Test safe_json fuzzer with inputs
    fuzz_safe_json(b'{"nested": [{"a": 1}]}')
    fuzz_safe_json(b"[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]")
    fuzz_safe_json(b"\x00\xff\xfe\x1b")

    # Test variant detector fuzzer
    fuzz_variant_detector(b"SGVsbG8gV29ybGQ=")
    fuzz_variant_detector(b"random gibberish%00%ff\x1b[31m")

    # Test zip guard fuzzer
    fuzz_zip_guard(b"PK\x03\x04fakezipheader")


if __name__ == "__main__":
    if atheris is None:
        print("Atheris not installed. Install with 'pip install atheris' on Linux to run.")
        sys.exit(0)

    atheris.instrument_all()
    # By default fuzz safe_json
    atheris.Setup(sys.argv, fuzz_safe_json)
    atheris.Fuzz()

