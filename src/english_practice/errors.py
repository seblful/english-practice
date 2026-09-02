"""Exception hierarchy for the application.

Every error the application raises on purpose derives from
:class:`EnglishPracticeError`, so callers can catch the whole family without
resorting to bare ``except Exception``.
"""


class EnglishPracticeError(Exception):
    """Base class for every error raised by this application."""


class ConfigurationError(EnglishPracticeError):
    """A setting is missing or invalid, so the operation cannot be attempted."""


class AgentError(EnglishPracticeError):
    """An LLM call failed or returned something unusable."""
