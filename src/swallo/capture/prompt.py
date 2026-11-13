"""
Structured paste prompt generation for chat LLMs.

Per TRD.md section 6.1, CLI_AND_MCP_SPEC.md section 1, and COMMANDS.md:
- Generates a structured prompt to paste into a chat model (ChatGPT, Claude, Gemini).
- Instructs the model to distill conversation context into a valid swallo v0.1 JSON packet.
- Embeds strict safety guidelines: no filler, no raw secrets, valid item kinds.
- Works offline with zero network calls.
"""

from __future__ import annotations

import typing
from datetime import UTC, datetime

from swallo.schema.models import Item


def get_valid_item_kinds() -> list[str]:
    """Dynamically extract the valid item kinds defined on the Pydantic Item model."""
    annotation = Item.model_fields["kind"].annotation
    return list(typing.get_args(annotation))


def generate_handoff_prompt(
    target: str = "claude_code",
    project: str = "default",
) -> str:
    """
    Generate the structured-paste prompt to instruct a chat model to output a swallo packet.
    """
    target_descriptions: dict[str, str] = {
        "claude_code": "Claude Code IDE agent",
        "cursor": "Cursor IDE assistant (.cursorrules)",
        "antigravity": "Antigravity coding assistant",
        "chat": "subsequent chat conversation",
    }
    target_label = target_descriptions.get(target, f"{target} IDE assistant")

    valid_kinds = get_valid_item_kinds()
    formatted_kinds = ", ".join(f'"{k}"' for k in valid_kinds)

    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    return f"""Please summarize the decisions, constraints, questions, and references from our \
conversation into a structured Swallo context handoff packet for delivery to a {target_label}.

Return ONLY a single valid JSON object matching the Swallo schema v0.1 below.
Do not include markdown conversational filler, greetings, or explanations before or after the JSON.

```json
{{
  "schema_version": "0.1",
  "project": "{project}",
  "created_at": "{now_iso}",
  "sources": [
    {{
      "session_id": "session_handoff",
      "agent": "{target}",
      "capture_method": "paste",
      "captured_at": "{now_iso}"
    }}
  ],
  "goal": {{
    "text": "<Concise summary of the objective or problem being solved>"
  }},
  "items": [
    {{
      "kind": "decision",
      "text": "<A specific architectural, design, or algorithmic decision made in this session>"
    }},
    {{
      "kind": "constraint",
      "text": "<A hard boundary, invariant, or constraint to respect (e.g. no extra dependencies)>"
    }},
    {{
      "kind": "question",
      "text": "<An open question or unresolved inquiry for the receiving agent>"
    }},
    {{
      "kind": "artifact_ref",
      "text": "<Reference to a relevant file, commit, ticket, or artifact>"
    }}
  ]
}}
```

CRITICAL INSTRUCTIONS:
1. Valid item kinds are strictly: {formatted_kinds}.
2. Never include confidential secrets, live API keys, credentials, or private tokens.
3. Be specific, factual, and concise. Omit general programming advice.
4. Output raw JSON only.
"""
