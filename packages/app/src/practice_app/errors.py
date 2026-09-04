"""Exception hierarchy for the app."""

from practice_core.errors import (
    ConfigurationError,
    ContentError,
    GradingError,
    PracticeError,
)

__all__ = [
    "ConfigurationError",
    "ContentError",
    "GradingError",
    "PracticeError",
    "ProviderError",
]


class ProviderError(PracticeError):
    """A call to the LLM provider failed or returned something unusable."""
