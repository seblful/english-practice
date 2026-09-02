"""Exception hierarchy for the bot.

Every error the application raises on purpose derives from
:class:`EnglishPracticeError`, so callers can catch the whole family without
resorting to bare ``except Exception``.

The root and the errors the Android app also raises come from
:mod:`practice_core.errors`; the bot adds the ones only it can hit.
``EnglishPracticeError`` is that shared root under the name the bot has always
used for it.
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
    "EnglishPracticeError",
    "GradingError",
]

EnglishPracticeError = PracticeError


class AgentError(PracticeError):
    """An LLM call failed or returned something unusable."""
