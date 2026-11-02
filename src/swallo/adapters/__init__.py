"""
Adapters for delivering context packets to target IDE environments and chat.
"""

from __future__ import annotations

from swallo.adapters.base import (
    BaseAdapter,
    DeliveryResult,
    compute_file_sha256,
    update_marker_block,
)
from swallo.adapters.chat import ChatAdapter
from swallo.adapters.claude_code import ClaudeCodeAdapter
from swallo.adapters.registry import (
    get_adapter,
    list_supported_targets,
    normalize_target,
)

__all__ = [
    "BaseAdapter",
    "ChatAdapter",
    "ClaudeCodeAdapter",
    "DeliveryResult",
    "compute_file_sha256",
    "get_adapter",
    "list_supported_targets",
    "normalize_target",
    "update_marker_block",
]
