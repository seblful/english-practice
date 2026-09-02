"""Signature-preserving wrapper around LangSmith's ``traceable`` decorator."""

from collections.abc import Callable
from typing import Any, Protocol, cast

from langsmith import traceable as _traceable


class _SignaturePreservingDecorator(Protocol):
    """A decorator that returns the function it wraps, unchanged in type."""

    def __call__[F: Callable[..., Any]](self, func: F) -> F:
        """Wrap ``func`` without altering its signature."""
        ...


def traced(**kwargs: Any) -> _SignaturePreservingDecorator:
    """Return a signature-preserving LangSmith tracing decorator.

    ``langsmith.traceable`` returns a ``SupportsLangsmithExtra`` wrapper whose
    ParamSpec-based ``__call__`` defeats keyword-argument type checking at every
    call site — langsmith carries an upstream ``type: ignore`` on it. Presenting
    the decorator as signature-preserving restores that checking without
    changing any runtime behaviour: the object returned here is langsmith's own.

    Args:
        **kwargs: Forwarded to ``langsmith.traceable`` (for example ``name``).

    Returns:
        A decorator that traces the wrapped function and keeps its signature.
    """
    return cast("_SignaturePreservingDecorator", _traceable(**kwargs))
