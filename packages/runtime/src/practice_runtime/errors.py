"""Errors raised by the runtime."""

from practice_core.errors import (
    ConfigurationError,
    ContentError,
    GradingError,
    PracticeError,
)

__all__ = [
    "AgentError",
    "ConfigurationError",
    "ContentError",
    "GradingError",
    "PracticeError",
]


class AgentError(PracticeError):
    """An LLM call failed or returned something unusable."""
