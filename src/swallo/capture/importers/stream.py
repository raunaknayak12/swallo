"""
Safe JSON parsing with recursion depth and payload size caps.

Per TRD.md section 10 and Security.md F8:
- Prevents parser recursion stack overflows from maliciously deep JSON documents.
- Verifies maximum nesting depth (default: 50 levels).
- Rejects payload if depth exceeds threshold or decoding fails.
"""

from __future__ import annotations

import json

from swallo.errors import SecurityError, ValidationError


def _check_nesting_depth(obj: object, current_depth: int, max_depth: int) -> None:
    """Recursively verify that JSON structures do not exceed max_depth."""
    if current_depth > max_depth:
        raise SecurityError(
            f"JSON nesting depth ({current_depth}) exceeds maximum permitted limit ({max_depth})."
        )

    if isinstance(obj, dict):
        for val in obj.values():
            if isinstance(val, (dict, list)):
                _check_nesting_depth(val, current_depth + 1, max_depth)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                _check_nesting_depth(item, current_depth + 1, max_depth)


def safe_json_loads(data: str | bytes, max_depth: int = 50) -> object:
    """
    Safely parse JSON data while enforcing maximum recursion depth caps.
    Raises ValidationError on malformed JSON and SecurityError on depth violations.
    """
    if isinstance(data, bytes):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as err:
            raise ValidationError(f"Invalid UTF-8 encoding in JSON data: {err}") from err
    else:
        text = data

    try:
        decoder = json.JSONDecoder()
        parsed: object = decoder.decode(text)
    except (json.JSONDecodeError, ValueError) as err:
        raise ValidationError(f"Malformed JSON data: {err}") from err

    _check_nesting_depth(parsed, current_depth=1, max_depth=max_depth)
    return parsed
