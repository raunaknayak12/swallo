"""
Validation constants and bounds for swallo context packets.

Per PACKET_SCHEMA.md section 7.
"""

from __future__ import annotations

# Max characters in an item text field
MAX_ITEM_TEXT_LEN = 2000

# Max items of a single kind in a packet
MAX_ITEMS_PER_KIND = 500

# Max total packet size in bytes (1 MiB)
MAX_PACKET_BYTES = 1024 * 1024

# Max JSON nesting depth
MAX_JSON_DEPTH = 16

# Supported schema versions
CURRENT_SCHEMA_VERSION = "0.1"
SUPPORTED_SCHEMA_VERSIONS = ("0.1",)
