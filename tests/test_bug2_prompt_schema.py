"""
Bug 2 regression tests: `swallo prompt` must not contradict the save schema.

Tests FAIL before fix (prompt hardcodes wrong kinds/missing fields).
Tests PASS after fix (prompt derives kinds from Pydantic model, sample JSON is valid).
"""

from __future__ import annotations

import json
import re
import typing

import pytest

from swallo.capture.prompt import generate_handoff_prompt
from swallo.schema.models import Item, Packet

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_KINDS = list(typing.get_args(Item.model_fields["kind"].annotation))

# Snapshot: the canonical list of valid kinds as of when the fix is applied.
# Update this constant only when the schema intentionally changes.
SNAPSHOT_KINDS = ["decision", "constraint", "question", "artifact_ref"]


def _extract_kinds_from_prompt(prompt_text: str) -> list[str]:
    """Return the list of kind values mentioned in the CRITICAL INSTRUCTIONS block."""
    match = re.search(
        r"Valid item kinds are strictly:\s*(.*?)(?:\n|\.)", prompt_text
    )
    if not match:
        return []
    raw = match.group(1)
    # Strip surrounding quotes and split on commas/whitespace
    return [k.strip().strip('"').strip("'") for k in raw.split(",") if k.strip()]


def _extract_json_block(prompt_text: str) -> dict:
    """Extract the first ```json ... ``` block from the prompt text and return parsed JSON."""
    match = re.search(r"```json\s*(\{.*?\})\s*```", prompt_text, re.DOTALL)
    if not match:
        raise ValueError("No JSON block found in prompt text")
    return json.loads(match.group(1))


# ---------------------------------------------------------------------------
# (b) Every kind listed in CRITICAL INSTRUCTIONS must be accepted by Item.kind
# ---------------------------------------------------------------------------


def test_prompt_kinds_all_valid_in_model() -> None:
    """Every kind mentioned in CRITICAL INSTRUCTIONS must be in Item.kind Literal."""
    prompt_text = generate_handoff_prompt()
    prompt_kinds = _extract_kinds_from_prompt(prompt_text)

    assert prompt_kinds, "Could not extract kinds from CRITICAL INSTRUCTIONS block"

    invalid = [k for k in prompt_kinds if k not in VALID_KINDS]
    assert not invalid, (
        f"Prompt CRITICAL INSTRUCTIONS lists kinds not accepted by Item.kind: {invalid}. "
        f"Valid kinds are: {VALID_KINDS}"
    )


# ---------------------------------------------------------------------------
# (c) Every kind in Item.kind Literal must appear in the prompt output
# ---------------------------------------------------------------------------


def test_prompt_includes_all_model_kinds() -> None:
    """Every valid Item.kind must appear somewhere in the generated prompt."""
    prompt_text = generate_handoff_prompt()

    missing = [k for k in VALID_KINDS if k not in prompt_text]
    assert not missing, (
        f"Prompt does not mention these valid kinds: {missing}. "
        f"All valid kinds must appear in the prompt so users know to use them."
    )


# ---------------------------------------------------------------------------
# (a) Sample JSON block must be parseable and validate against Packet
# ---------------------------------------------------------------------------


def test_prompt_sample_json_validates_against_packet_model() -> None:
    """The sample JSON in the prompt must pass Packet.model_validate() without errors."""
    prompt_text = generate_handoff_prompt()
    sample = _extract_json_block(prompt_text)

    # Must not raise
    try:
        Packet.model_validate(sample)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"Sample JSON in prompt does not validate against Packet model: {exc}\n"
            f"Sample JSON: {json.dumps(sample, indent=2)}"
        )


def test_prompt_sample_json_has_required_fields() -> None:
    """Sample JSON must include all Packet required fields: created_at, sources, project, goal."""
    prompt_text = generate_handoff_prompt()
    sample = _extract_json_block(prompt_text)

    required = ["schema_version", "project", "goal", "sources", "created_at"]
    missing = [f for f in required if f not in sample]
    assert not missing, (
        f"Sample JSON in prompt is missing required Packet fields: {missing}"
    )


def test_prompt_sample_json_item_kinds_are_valid() -> None:
    """Every item in the sample JSON must use a valid Item.kind."""
    prompt_text = generate_handoff_prompt()
    sample = _extract_json_block(prompt_text)

    items = sample.get("items", [])
    assert items, "Sample JSON has no items"

    invalid = [item.get("kind") for item in items if item.get("kind") not in VALID_KINDS]
    assert not invalid, (
        f"Sample JSON contains items with invalid kinds: {invalid}. "
        f"Valid kinds: {VALID_KINDS}"
    )


# ---------------------------------------------------------------------------
# (d) Snapshot test: kind list must not silently change
# ---------------------------------------------------------------------------


def test_valid_kinds_snapshot() -> None:
    """Fail if the set of valid Item kinds changes without updating SNAPSHOT_KINDS."""
    assert VALID_KINDS == SNAPSHOT_KINDS, (
        f"Item.kind Literal changed!\n"
        f"  Current: {VALID_KINDS}\n"
        f"  Snapshot: {SNAPSHOT_KINDS}\n"
        "Update SNAPSHOT_KINDS in this file to acknowledge the change."
    )


def test_prompt_kinds_snapshot() -> None:
    """Fail if the prompt CRITICAL INSTRUCTIONS kind list changes without updating snapshot."""
    prompt_text = generate_handoff_prompt()
    prompt_kinds = _extract_kinds_from_prompt(prompt_text)

    assert prompt_kinds == SNAPSHOT_KINDS, (
        f"Prompt CRITICAL INSTRUCTIONS kind list changed or diverged from snapshot!\n"
        f"  Prompt kinds: {prompt_kinds}\n"
        f"  Snapshot: {SNAPSHOT_KINDS}\n"
        "Update SNAPSHOT_KINDS in this file to acknowledge the change."
    )
