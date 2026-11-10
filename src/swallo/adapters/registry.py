"""
Registry of target adapters for delivering context packets.

Per CLI_AND_MCP_SPEC.md and TRD.md §7:
- Maps target names (e.g. 'claude-code', 'chat') to adapter instances.
- Normalizes names (case-insensitive, hyphen/underscore normalization).
- Validates targets and raises UsageError for unknown targets.
"""

from __future__ import annotations

from swallo.adapters.antigravity import AntigravityAdapter
from swallo.adapters.base import BaseAdapter
from swallo.adapters.chat import ChatAdapter
from swallo.adapters.claude_code import ClaudeCodeAdapter
from swallo.errors import UsageError

# Registry mapping canonical target name to adapter class
_ADAPTER_CLASSES: dict[str, type[BaseAdapter]] = {
    "claude-code": ClaudeCodeAdapter,
    "antigravity": AntigravityAdapter,
    "chat": ChatAdapter,
}

# Aliases for convenience
_ALIASES: dict[str, str] = {
    "claude_code": "claude-code",
    "claude": "claude-code",
    "agy": "antigravity",
    "gemini": "antigravity",
}


def normalize_target(target: str) -> str:
    """Normalize a target name string."""
    key = target.strip().lower()
    return _ALIASES.get(key, key)


def list_supported_targets() -> list[str]:
    """Return sorted list of supported target names."""
    return sorted(_ADAPTER_CLASSES.keys())


def get_adapter(target: str) -> BaseAdapter:
    """
    Look up an adapter instance for the specified target.

    Args:
        target: Target name (e.g. 'claude-code', 'chat').

    Returns:
        BaseAdapter instance.

    Raises:
        UsageError: If target is not supported.
    """
    normalized = normalize_target(target)
    adapter_cls = _ADAPTER_CLASSES.get(normalized)
    if adapter_cls is None:
        supported = ", ".join(list_supported_targets())
        raise UsageError(
            f"Unsupported delivery target '{target}'. Supported targets: {supported}"
        )
    return adapter_cls()
