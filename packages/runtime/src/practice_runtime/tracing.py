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
    """Return a signature-preserving LangSmith tracing decorator."""
    return cast("_SignaturePreservingDecorator", _traceable(**kwargs))
