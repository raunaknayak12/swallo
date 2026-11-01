"""
Controlling terminal detection and human interactive confirmation.

Per IMPLEMENTATION_PLAN.md Step 3 and Security.md F21:
- Prompts for human confirmation (e.g. during packet approval or forced init).
- Reads directly from the controlling terminal (/dev/tty on POSIX, CONIN$ on Windows)
  rather than sys.stdin, preventing piped or redirected script input from bypassing prompts.
- Acknowledges that terminal detection is best-effort defense against accidental automation,
  not proof of human presence (compromised agents with local subshell access can allocate a PTY).
"""

from __future__ import annotations

import sys
from typing import TextIO

from swallo.errors import UsageError


def is_terminal_available() -> bool:
    """Check if a controlling terminal device or interactive console is accessible."""
    if sys.platform == "win32":
        try:
            with open("CONIN$") as f:
                return f.isatty()
        except OSError:
            return sys.stdin.isatty()
    else:
        try:
            with open("/dev/tty") as f:
                return f.isatty()
        except OSError:
            return sys.stdin.isatty()


def confirm_on_terminal(
    prompt: str,
    default: bool = False,
    stream_in: TextIO | None = None,
    stream_out: TextIO | None = None,
) -> bool:
    """
    Prompt the user for interactive confirmation on the controlling terminal.

    Args:
        prompt: Question to ask the user.
        default: Return value if user hits Enter without input.
        stream_in: Optional override for input (for testing).
        stream_out: Optional override for output (for testing).

    Raises:
        UsageError: If no controlling terminal is available and input is piped.
    """
    suffix = "[Y/n]" if default else "[y/N]"
    full_prompt = f"{prompt} {suffix}: "

    # Case 1: Injected streams (e.g. during automated unit tests)
    if stream_in is not None:
        out = stream_out or sys.stdout
        out.write(full_prompt)
        out.flush()
        line = stream_in.readline()
        if not line:
            return default
        answer = line.strip().lower()
        if not answer:
            return default
        return answer in ("y", "yes")

    # Case 2: Controlling terminal on Windows (CONIN$ / CONOUT$)
    if sys.platform == "win32":
        try:
            with open("CONOUT$", "w") as conout, open("CONIN$") as conin:
                conout.write(full_prompt)
                conout.flush()
                raw = conin.readline()
                answer = raw.strip().lower() if raw else ""
                if not answer:
                    return default
                return answer in ("y", "yes")
        except OSError:
            pass

    # Case 3: Controlling terminal on POSIX (/dev/tty)
    else:
        try:
            with open("/dev/tty", "r+") as tty:
                tty.write(full_prompt)
                tty.flush()
                raw = tty.readline()
                answer = raw.strip().lower() if raw else ""
                if not answer:
                    return default
                return answer in ("y", "yes")
        except OSError:
            pass

    # Fallback check: If sys.stdin is an interactive terminal
    if sys.stdin.isatty() and sys.stdout.isatty():
        sys.stdout.write(full_prompt)
        sys.stdout.flush()
        raw = sys.stdin.readline()
        answer = raw.strip().lower() if raw else ""
        if not answer:
            return default
        return answer in ("y", "yes")

    # If completely non-interactive and no terminal is present, fail securely
    raise UsageError(
        "Interactive human approval required, but controlling terminal is not available "
        "(input is piped or environment is headless)."
    )
