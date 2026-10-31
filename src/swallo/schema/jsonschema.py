"""
JSON Schema export utilities for swallo context packet models.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from swallo.schema.models import Packet


def export_json_schema() -> dict[str, Any]:
    """Generate JSON schema dictionary from the Packet Pydantic model."""
    schema = Packet.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return schema


def dump_json_schema(indent: int = 2) -> str:
    """Return the JSON schema as a formatted JSON string."""
    return json.dumps(export_json_schema(), indent=indent)


def write_json_schema(dest: Path | str) -> Path:
    """Write the JSON schema to destination path."""
    path = Path(dest)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = dump_json_schema()
    path.write_text(content + "\n", encoding="utf-8")
    return path
