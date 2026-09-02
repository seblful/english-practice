"""Exception hierarchy shared by both front ends.

Every error either side raises on purpose derives from :class:`PracticeError`,
so a caller can catch the whole family without resorting to bare
``except Exception``. Each front end adds its own leaves — the bot an
``AgentError``, the app a ``ProviderError`` — under the same root.
"""


class PracticeError(Exception):
    """Base class for every error the application raises deliberately."""


class ConfigurationError(PracticeError):
    """A setting is missing or invalid, so the operation cannot be attempted."""


class ContentError(PracticeError):
    """The exercise database is missing, unreadable, or malformed."""


class GradingError(PracticeError):
    """A grading verdict could not be read back from a model's reply."""
