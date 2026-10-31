"""
Tests and golden verification for swallo canonical JSON v1.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from swallo.errors import ValidationError
from swallo.schema.canonical import canonicalize, parse_canonical_json

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_golden_canonical_v1() -> None:
    golden_path = FIXTURES_DIR / "golden_canonical_v1.json"
    golden_bytes = golden_path.read_bytes()

    # Dictionary initialized with arbitrary key ordering
    data = {
        "gamma": "café",
        "beta": True,
        "alpha": 1,
        "delta": None,
        "list": [-100, 0, 100],
        "epsilon": {"nested_key": "value"},
    }

    result = canonicalize(data)
    assert result == golden_bytes


def test_canonicalize_sorted_keys() -> None:
    dict1 = {"b": 2, "a": 1, "c": 3}
    dict2 = {"a": 1, "c": 3, "b": 2}
    expected = b'{"a":1,"b":2,"c":3}'

    assert canonicalize(dict1) == expected
    assert canonicalize(dict2) == expected


def test_canonicalize_nfc_normalization() -> None:
    # NFD: "e" + combining acute accent (\u0301)
    decomposed = "e\u0301cole"
    # NFC: precomposed "é" (\u00e9)
    precomposed = "\u00e9cole"

    assert decomposed != precomposed
    assert canonicalize({"text": decomposed}) == canonicalize({"text": precomposed})
    assert canonicalize({"text": decomposed}) == b'{"text":"\xc3\xa9cole"}'


def test_canonicalize_rejects_floats() -> None:
    with pytest.raises(ValidationError, match="Floating-point"):
        canonicalize({"float_val": 1.23})

    with pytest.raises(ValidationError, match="Floating point"):
        parse_canonical_json('{"float_val": 1.23}')

    with pytest.raises(ValidationError, match="Floating point"):
        parse_canonical_json('{"float_val": 1e10}')


def test_canonicalize_integer_bounds() -> None:
    # Exactly at boundary 2^53 - 1
    max_safe = 9007199254740991
    min_safe = -9007199254740991

    assert canonicalize({"val": max_safe}) == f'{{"val":{max_safe}}}'.encode()
    assert canonicalize({"val": min_safe}) == f'{{"val":{min_safe}}}'.encode()

    # Beyond boundary
    with pytest.raises(ValidationError, match="exceeds canonical JSON bounds"):
        canonicalize({"val": max_safe + 1})

    with pytest.raises(ValidationError, match="exceeds canonical JSON bounds"):
        canonicalize({"val": min_safe - 1})


def test_parse_canonical_rejects_duplicate_keys() -> None:
    with pytest.raises(ValidationError, match="Duplicate object key"):
        parse_canonical_json('{"key": 1, "key": 2}')


def test_parse_canonical_rejects_bom() -> None:
    bom_bytes = b'\xef\xbb\xbf{"key": 1}'
    with pytest.raises(ValidationError, match="byte order mark"):
        parse_canonical_json(bom_bytes)

    bom_str = '\ufeff{"key": 1}'
    with pytest.raises(ValidationError, match="byte order mark"):
        parse_canonical_json(bom_str)


def test_canonicalize_rejects_lone_surrogates() -> None:
    lone_surrogate = "\ud800"
    with pytest.raises(ValidationError, match="lone surrogates"):
        canonicalize({"text": lone_surrogate})


def test_canonicalize_idempotent() -> None:
    data = {"hello": "world", "count": 42, "items": [1, 2, 3]}
    bytes1 = canonicalize(data)
    parsed = parse_canonical_json(bytes1)
    bytes2 = canonicalize(parsed)
    assert bytes1 == bytes2
