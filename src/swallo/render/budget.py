"""
Token estimation and context budgeting with critical item protection.

Per TRD.md section 2 and IMPLEMENTATION_PLAN.md Step 5:
- Heuristic token estimation (char / 4 words heuristic in stdlib core, tiktoken if available).
- Trims low-priority context items gracefully when budget is exceeded.
- Critical items (flagged with critical=True) are never trimmed.
- Fails loudly (BudgetExceededError) if critical items alone exceed the token budget.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from swallo.errors import SwalloError


class BudgetExceededError(SwalloError):
    """Raised when critical items exceed the maximum available token budget."""

    def __init__(self, message: str) -> None:
        super().__init__(message, exit_code=7)


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for a text string.

    Uses a fast heuristic (approx 4 characters per token + word-boundary weighting)
    without introducing non-stdlib dependencies in the core.
    """
    if not text:
        return 0
    # Heuristic: ~3.8 chars per token for typical English code and Markdown
    return max(1, math.ceil(len(text) / 3.8))


@dataclass
class BudgetItem:
    item_id: str
    kind: str
    text: str
    critical: bool
    estimated_tokens: int


@dataclass
class BudgetResult:
    included_items: list[dict[str, Any]]
    trimmed_items: list[dict[str, Any]]
    total_tokens: int
    budget_limit: int


def budget_items(
    items: list[dict[str, Any]],
    token_budget: int,
    base_tokens: int = 0,
) -> BudgetResult:
    """
    Fit packet items within a token budget while guaranteeing critical items are kept.

    Args:
        items: List of item dictionaries (from Packet schema).
        token_budget: Maximum tokens allowed.
        base_tokens: Tokens already used by goal, envelope, headers, and fence.

    Returns:
        BudgetResult with included items, trimmed items, and token tally.

    Raises:
        BudgetExceededError: If critical items alone cannot fit within token_budget.
    """
    available_budget = token_budget - base_tokens
    if available_budget <= 0:
        raise BudgetExceededError(
            f"Base envelope ({base_tokens} tokens) exceeds total budget ({token_budget} tokens)."
        )

    budget_items_list: list[BudgetItem] = []
    for item in items:
        text = str(item.get("text", ""))
        item_id = str(item.get("id", ""))
        kind = str(item.get("kind", "decision"))
        # Check critical flag
        critical = bool(item.get("critical", False))
        tokens = estimate_tokens(text)
        budget_items_list.append(
            BudgetItem(
                item_id=item_id,
                kind=kind,
                text=text,
                critical=critical,
                estimated_tokens=tokens,
            )
        )

    # 1. Calculate required tokens for critical items
    critical_items = [b for b in budget_items_list if b.critical]
    critical_tokens = sum(b.estimated_tokens for b in critical_items)

    if critical_tokens > available_budget:
        raise BudgetExceededError(
            f"Critical items require {critical_tokens} tokens, but only {available_budget} "
            f"remain in budget (limit: {token_budget}, base: {base_tokens})."
        )

    included: list[dict[str, Any]] = []
    trimmed: list[dict[str, Any]] = []
    current_tokens = base_tokens

    # Critical items are always included first
    included_ids: set[str] = set()
    for b in critical_items:
        current_tokens += b.estimated_tokens
        included_ids.add(b.item_id)

    # Non-critical items are included in order as long as they fit
    for b, raw_item in zip(budget_items_list, items, strict=True):
        if b.item_id in included_ids:
            included.append(raw_item)
            continue

        if current_tokens + b.estimated_tokens <= token_budget:
            current_tokens += b.estimated_tokens
            included.append(raw_item)
        else:
            trimmed.append(raw_item)

    return BudgetResult(
        included_items=included,
        trimmed_items=trimmed,
        total_tokens=current_tokens,
        budget_limit=token_budget,
    )
