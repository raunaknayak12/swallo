"""
swallo canonical JSON v1 implementation.

Per ADR-024 and PACKET_SCHEMA.md section 6:
- UTF-8 without BOM; no insignificant whitespace; separators ',' and ':'.
- Object keys sorted by Unicode code point; duplicate keys rejected at parse time.
- Strings normalized to NFC at ingest and encoded with ensure_ascii=False; lone surrogates rejected.
- Integers only within +/-(2^53 - 1). Floats, NaN and Infinity rejected anywhere.
"""

from __future__ import annotations

import json
import unicodedata

from swallo.errors import ValidationError

# Safe integer range within IEEE-754 double precision integers: +/-(2^53 - 1)
MAX_CANONICAL_INT = 9007199254740991
MIN_CANONICAL_INT = -9007199254740991


def _check_string(s: str) -> str:
    # Reject lone surrogates (\ud800 - \udfff)
    try:
        s.encode("utf-8")
    except UnicodeEncodeError as err:
        raise ValidationError(f"String contains invalid Unicode or lone surrogates: {err}") from err
    return unicodedata.normalize("NFC", s)


def _clean_value(val: object) -> object:
    # Notice: bool is a subclass of int in Python, so check bool first!
    if isinstance(val, bool):
        return val
    if isinstance(val, int):
        if val < MIN_CANONICAL_INT or val > MAX_CANONICAL_INT:
            msg = (
                f"Integer {val} exceeds canonical JSON bounds "
                f"[{MIN_CANONICAL_INT}, {MAX_CANONICAL_INT}]"
            )
            raise ValidationError(msg)
        return val
    if isinstance(val, float):
        raise ValidationError(f"Floating-point numbers are prohibited in canonical JSON: {val}")
    if isinstance(val, str):
        return _check_string(val)
    if val is None:
        return None
    if isinstance(val, (list, tuple)):
        return [_clean_value(item) for item in val]
    if isinstance(val, dict):
        clean_dict: dict[str, object] = {}
        for k, v in val.items():
            if not isinstance(k, str):
                raise ValidationError(f"Object keys must be strings, got {type(k).__name__}")
            norm_key = _check_string(k)
            if norm_key in clean_dict:
                raise ValidationError(f"Duplicate key after NFC normalization: {norm_key!r}")
            clean_dict[norm_key] = _clean_value(v)
        # Python 3.7+ preserves insertion order; sorting keys ensures code point order
        return {k: clean_dict[k] for k in sorted(clean_dict.keys())}
    raise ValidationError(f"Unsupported type for canonical JSON: {type(val).__name__}")


def canonicalize(value: object) -> bytes:
    """
    Produce canonical JSON bytes for a Python value.

    Returns deterministic UTF-8 bytes with no insignificant whitespace and sorted keys.
    """
    clean_val = _clean_value(value)
    serialized = json.dumps(
        clean_val,
        separators=(",", ":"),
        ensure_ascii=False,
        sort_keys=True,
    )
    return serialized.encode("utf-8")


def _reject_float(s: str) -> None:
    raise ValidationError(f"Floating point numbers are forbidden in canonical JSON: {s!r}")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    res: dict[str, object] = {}
    for k, v in pairs:
        norm_key = _check_string(k)
        if norm_key in res:
            raise ValidationError(f"Duplicate object key in JSON: {k!r}")
        res[norm_key] = v
    return res


def parse_canonical_json(raw: str | bytes) -> object:
    """
    Parse a JSON string or bytes, strictly rejecting duplicate keys, floats, and invalid UTF-8.
    """
    if isinstance(raw, bytes):
        if raw.startswith(b"\xef\xbb\xbf"):
            raise ValidationError("UTF-8 byte order mark (BOM) is forbidden in canonical JSON")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as err:
            raise ValidationError(f"Invalid UTF-8 encoding: {err}") from err
    else:
        text = raw
        if text.startswith("\ufeff"):
            raise ValidationError("UTF-8 byte order mark (BOM) is forbidden in canonical JSON")

    try:
        parsed = json.loads(
            text,
            parse_float=_reject_float,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except json.JSONDecodeError as err:
        raise ValidationError(f"Malformed JSON: {err}") from err

    # Recursively check integer bounds and string NFC normalization
    return _clean_value(parsed)
