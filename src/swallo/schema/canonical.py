"""
swallo canonical JSON v1 implementation.

Per ADR-024 and PACKET_SCHEMA.md section 6:
- UTF-8 without BOM; no insignificant whitespace; separators ',' and ':'.
- Object keys sorted by Unicode code point; duplicate keys rejected at parse time.
- Strings normalized to NFC at ingest and encoded with ensure_ascii=False; lone surrogates rejected.
- Integers only within +/-(2^53 - 1). Floats, NaN and Infinity rejected anywhere.
"""

from __future__ import annotations

import hashlib
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
        decoder = json.JSONDecoder(
            parse_float=_reject_float,
            object_pairs_hook=_reject_duplicate_keys,
        )
        parsed = decoder.decode(text)
    except (json.JSONDecodeError, ValueError) as err:
        raise ValidationError(f"Malformed JSON: {err}") from err

    # Recursively check integer bounds and string NFC normalization
    return _clean_value(parsed)


def hashed_form(packet: dict[str, object]) -> dict[str, object]:
    """
    Produce the hashed form of a packet by excluding volatile fields.

    Per PACKET_SCHEMA.md section 6:
    Excludes top-level 'id', 'created_at', and every 'sources[*].captured_at'.
    """
    if not isinstance(packet, dict):
        raise ValidationError(f"Expected packet dict, got {type(packet).__name__}")

    out: dict[str, object] = {}
    for k, v in packet.items():
        if k in ("id", "created_at"):
            continue
        if k == "sources" and isinstance(v, list):
            clean_sources: list[object] = []
            for src in v:
                if isinstance(src, dict):
                    clean_src = {sk: sv for sk, sv in src.items() if sk != "captured_at"}
                    clean_sources.append(clean_src)
                else:
                    clean_sources.append(src)
            out[k] = clean_sources
        else:
            out[k] = v
    return out


def packet_hash(packet: dict[str, object]) -> str:
    """
    Compute sha256 hex digest of the canonical bytes of the packet's hashed form.
    """
    h_form = hashed_form(packet)
    canonical_bytes = canonicalize(h_form)
    digest = hashlib.sha256(canonical_bytes).hexdigest()
    return f"sha256:{digest}"


def derive_packet_id(hash_: str, taken: set[str] | None = None) -> str:
    """
    Derive packet ID: 'pkt_' + first 12 hex characters of the hash.

    Extends by 2 characters on collision with a different hash in the store.
    """
    raw_hex = hash_.removeprefix("sha256:")
    if len(raw_hex) < 12:
        raise ValidationError(f"Invalid packet hash length: {hash_!r}")

    length = 12
    candidate = f"pkt_{raw_hex[:length]}"
    if taken is not None:
        while candidate in taken and length + 2 <= len(raw_hex):
            length += 2
            candidate = f"pkt_{raw_hex[:length]}"
    return candidate


def derive_item_id(kind: str, text: str, taken: set[str] | None = None) -> str:
    """
    Derive item ID: 'it_' + first 8 hex of SHA-256(kind, NUL, NFC text).

    Extends by 2 characters on collision within a packet.
    """
    nfc_text = unicodedata.normalize("NFC", text)
    payload = f"{kind}\0{nfc_text}".encode()
    digest = hashlib.sha256(payload).hexdigest()

    length = 8
    candidate = f"it_{digest[:length]}"
    if taken is not None:
        while candidate in taken and length + 2 <= len(digest):
            length += 2
            candidate = f"it_{digest[:length]}"
    return candidate
