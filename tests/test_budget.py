"""
Unit tests for token estimation and context budgeting with critical item protection.
"""

from __future__ import annotations

import pytest

from swallo.render.budget import (
    BudgetExceededError,
    budget_items,
    estimate_tokens,
)


def test_estimate_tokens_empty_and_normal() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("hello") >= 1
    long_text = "This is a detailed decision about using SQLite WAL mode for concurrency."
    toks = estimate_tokens(long_text)
    assert 10 <= toks <= 30


def test_budget_items_fits_all() -> None:
    items = [
        {"id": "it_1", "kind": "decision", "text": "Use SQLite WAL.", "critical": False},
        {"id": "it_2", "kind": "constraint", "text": "No network in core.", "critical": True},
    ]
    res = budget_items(items, token_budget=500, base_tokens=50)
    assert len(res.included_items) == 2
    assert len(res.trimmed_items) == 0
    assert res.total_tokens > 50


def test_budget_items_trims_non_critical() -> None:
    items = [
        {"id": "it_1", "kind": "decision", "text": "A" * 400, "critical": False},
        {"id": "it_2", "kind": "constraint", "text": "B" * 50, "critical": True},
        {"id": "it_3", "kind": "decision", "text": "C" * 400, "critical": False},
    ]
    # token budget allows base + critical (~20 tokens) + maybe one big item (~110 tokens)
    res = budget_items(items, token_budget=160, base_tokens=20)
    # it_2 is critical -> MUST be included
    included_ids = [it["id"] for it in res.included_items]
    assert "it_2" in included_ids
    # One or more non-critical items should be trimmed
    assert len(res.trimmed_items) >= 1
    assert res.total_tokens <= 160


def test_budget_items_raises_when_critical_exceeds_budget() -> None:
    items = [
        {"id": "it_crit", "kind": "constraint", "text": "X" * 1000, "critical": True},
    ]
    with pytest.raises(BudgetExceededError, match="Critical items require"):
        budget_items(items, token_budget=50, base_tokens=10)


def test_budget_items_raises_when_base_exceeds_budget() -> None:
    items = [{"id": "it_1", "kind": "decision", "text": "Hi", "critical": False}]
    with pytest.raises(BudgetExceededError, match="Base envelope"):
        budget_items(items, token_budget=50, base_tokens=100)
