"""
Error hierarchy and standardized exit codes for swallo.
"""

from __future__ import annotations


class SwalloError(Exception):
    """Base exception for all swallo errors."""

    exit_code: int = 1

    def __init__(self, message: str, exit_code: int | None = None) -> None:
        super().__init__(message)
        if exit_code is not None:
            self.exit_code = exit_code


class UsageError(SwalloError):
    """Invalid command line arguments or commands (exit code 2)."""

    exit_code = 2


class ValidationError(SwalloError):
    """Schema or limit validation failure (exit code 3)."""

    exit_code = 3


class RedactionBlockedError(SwalloError):
    """Redaction blocked the operation in fail-closed mode (exit code 4)."""

    exit_code = 4


class ConflictError(SwalloError):
    """Unresolved packet merge conflicts (exit code 5)."""

    exit_code = 5


class NotApprovedError(SwalloError):
    """Requested packet is not approved for target (exit code 6)."""

    exit_code = 6


class StaleContextError(SwalloError):
    """Packet has critical drift and is blocked by stale policy (exit code 7)."""

    exit_code = 7


class IntegrityError(SwalloError):
    """Integrity failure in event log chain or store (exit code 8)."""

    exit_code = 8
