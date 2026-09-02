"""Errors raised by the runtime.

The root and the errors the Android app also raises come from
:mod:`practice_core.errors`; this adds the one only a program that calls an LLM
can hit. Re-exporting the rest means the bot and the pipeline have a single
module to import errors from, rather than choosing between two.
"""

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
