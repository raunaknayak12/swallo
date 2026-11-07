"""
Implementation of 'swallo prompt' command.

Per TRD.md section 6.1, CLI_AND_MCP_SPEC.md section 1, and COMMANDS.md:
- Generates a structured prompt to paste into chat agents (ChatGPT, Claude, Gemini).
- Emits instructions specifying the Swallo v0.1 JSON schema and safety constraints.
- Supports --target and --project options.
"""

from __future__ import annotations

import argparse
import json

from swallo.capture.prompt import generate_handoff_prompt


def run_prompt(argv: list[str]) -> int:
    """Entry point for 'swallo prompt'."""
    parser = argparse.ArgumentParser(
        prog="swallo prompt",
        description="Generate a structured handoff prompt to paste into a chat agent.",
    )
    parser.add_argument(
        "--target",
        default="claude_code",
        help="Target IDE/assistant (claude-code, cursor, antigravity, chat).",
    )
    parser.add_argument(
        "--project",
        default="default",
        help="Target project name embedded into prompt schema (default: default).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON containing the prompt string.",
    )

    args = parser.parse_args(argv)

    # Normalize target name (e.g. claude-code -> claude_code)
    target = args.target.replace("-", "_").lower()
    prompt_text = generate_handoff_prompt(target=target, project=args.project)

    if args.json:
        payload = {
            "target": target,
            "project": args.project,
            "prompt": prompt_text,
        }
        print(json.dumps(payload, indent=2))
    else:
        print(prompt_text)

    return 0
