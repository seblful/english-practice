"""Exception hierarchy for the app.

The root and the errors the bot also raises come from
:mod:`practice_core.errors`; the app adds the one only it can hit, because only
it talks to a provider over raw HTTP.

Every message here is written to be shown to the user as-is: on a phone there
is no log to consult, so "OpenRouter rejected the API key" has to reach the
screen intact.
"""

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
