"""Tests for adapter registry and target lookup."""

from __future__ import annotations

import pytest

from swallo.adapters.chat import ChatAdapter
from swallo.adapters.claude_code import ClaudeCodeAdapter
from swallo.adapters.registry import (
    get_adapter,
    list_supported_targets,
    normalize_target,
)
from swallo.errors import UsageError


class TestAdapterRegistry:
    def test_lookup_claude_code(self) -> None:
        adapter = get_adapter("claude-code")
        assert isinstance(adapter, ClaudeCodeAdapter)
        assert adapter.name == "claude-code"

    def test_lookup_alias_claude_code(self) -> None:
        adapter = get_adapter("claude_code")
        assert isinstance(adapter, ClaudeCodeAdapter)

        adapter2 = get_adapter("claude")
        assert isinstance(adapter2, ClaudeCodeAdapter)

    def test_lookup_chat(self) -> None:
        adapter = get_adapter("chat")
        assert isinstance(adapter, ChatAdapter)
        assert adapter.name == "chat"

    def test_unsupported_target_raises_usage_error(self) -> None:
        with pytest.raises(UsageError) as exc_info:
            get_adapter("nonexistent-target")
        assert "Unsupported delivery target 'nonexistent-target'" in str(exc_info.value)
        assert "claude-code" in str(exc_info.value)

    def test_list_supported_targets(self) -> None:
        targets = list_supported_targets()
        assert "claude-code" in targets
        assert "chat" in targets

    def test_normalize_target(self) -> None:
        assert normalize_target(" CLAUDE_CODE ") == "claude-code"
        assert normalize_target("chat") == "chat"
