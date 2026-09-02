"""Providers, thinking levels, and the request fragments they translate into.

The three providers expose reasoning through three unrelated request shapes —
OpenRouter nests it under ``reasoning``, OpenAI takes a bare
``reasoning_effort``, Gemini wants a token budget — so the app keeps one
:class:`ThinkingLevel` scale for the UI and does the translation here. Anything
provider-specific about *thinking* belongs in this module; anything
provider-specific about *transport* belongs in :mod:`practice.llm`.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

__all__ = [
    "ModelInfo",
    "Provider",
    "ThinkingLevel",
    "supported_thinking_levels",
    "thinking_payload",
    "thinking_token_headroom",
]


class Provider(StrEnum):
    """An LLM provider the app can talk to."""

    OPENROUTER = "openrouter"
    GEMINI = "gemini"
    OPENAI = "openai"

    @property
    def label(self) -> str:
        """Return the provider's name as it is written in its own docs."""
        return _PROVIDER_LABELS[self]

    @property
    def console_url(self) -> str:
        """Return the page where a user creates an API key."""
        return _CONSOLE_URLS[self]

    @property
    def default_model(self) -> str:
        """Return the model to start from before the user picks one."""
        return _DEFAULT_MODELS[self]

    @property
    def lists_models_anonymously(self) -> bool:
        """Whether the model catalogue can be fetched without an API key."""
        return self is Provider.OPENROUTER


_PROVIDER_LABELS: Final[dict[Provider, str]] = {
    Provider.OPENROUTER: "OpenRouter",
    Provider.GEMINI: "Google Gemini",
    Provider.OPENAI: "OpenAI",
}

_CONSOLE_URLS: Final[dict[Provider, str]] = {
    Provider.OPENROUTER: "https://openrouter.ai/keys",
    Provider.GEMINI: "https://aistudio.google.com/apikey",
    Provider.OPENAI: "https://platform.openai.com/api-keys",
}

_DEFAULT_MODELS: Final[dict[Provider, str]] = {
    Provider.OPENROUTER: "google/gemini-2.5-flash",
    Provider.GEMINI: "gemini-2.5-flash",
    Provider.OPENAI: "gpt-4.1-mini",
}


class ThinkingLevel(StrEnum):
    """How much reasoning to ask a model for, on one scale for every provider."""

    OFF = "off"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    DYNAMIC = "dynamic"

    @property
    def label(self) -> str:
        """Return the level's name for the UI."""
        return _THINKING_LABELS[self]

    @property
    def description(self) -> str:
        """Return one line explaining the trade-off this level makes."""
        return _THINKING_DESCRIPTIONS[self]


_THINKING_LABELS: Final[dict[ThinkingLevel, str]] = {
    ThinkingLevel.OFF: "Off",
    ThinkingLevel.MINIMAL: "Minimal",
    ThinkingLevel.LOW: "Low",
    ThinkingLevel.MEDIUM: "Medium",
    ThinkingLevel.HIGH: "High",
    ThinkingLevel.DYNAMIC: "Auto",
}

_THINKING_DESCRIPTIONS: Final[dict[ThinkingLevel, str]] = {
    ThinkingLevel.OFF: "No reasoning tokens - fastest and cheapest.",
    ThinkingLevel.MINIMAL: "A brief pass before answering.",
    ThinkingLevel.LOW: "Some reasoning; still quick.",
    ThinkingLevel.MEDIUM: "A balance of accuracy and speed.",
    ThinkingLevel.HIGH: "The most careful grading, slowest and dearest.",
    ThinkingLevel.DYNAMIC: "The model decides how long to think.",
}

# Gemini takes a token budget rather than a named effort. 0 disables thinking
# and -1 hands the decision to the model; the rest are budgets that keep a
# grading call well inside a flash model's output allowance.
_GEMINI_BUDGETS: Final[dict[ThinkingLevel, int]] = {
    ThinkingLevel.OFF: 0,
    ThinkingLevel.MINIMAL: 512,
    ThinkingLevel.LOW: 2048,
    ThinkingLevel.MEDIUM: 8192,
    ThinkingLevel.HIGH: 24576,
    ThinkingLevel.DYNAMIC: -1,
}

# OpenRouter and OpenAI share OpenAI's named efforts. "Auto" has no equivalent
# there: omitting the field is what "let the model decide" means, which is what
# OFF already does on a model that cannot reason, so the level is not offered.
_EFFORT_LEVELS: Final[tuple[ThinkingLevel, ...]] = (
    ThinkingLevel.OFF,
    ThinkingLevel.MINIMAL,
    ThinkingLevel.LOW,
    ThinkingLevel.MEDIUM,
    ThinkingLevel.HIGH,
)

_GEMINI_LEVELS: Final[tuple[ThinkingLevel, ...]] = (
    ThinkingLevel.OFF,
    ThinkingLevel.DYNAMIC,
    ThinkingLevel.LOW,
    ThinkingLevel.MEDIUM,
    ThinkingLevel.HIGH,
)

_MILLION = 1_000_000
_THOUSAND = 1_000


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """One entry of a provider's model catalogue.

    Only the fields the picker actually shows are kept: the catalogues run to
    several hundred entries and the rest of each entry is never read.
    """

    id: str
    name: str
    description: str = ""
    context_length: int | None = None
    supports_thinking: bool = False
    supports_images: bool = False
    supports_json: bool = False
    prompt_price: float | None = None
    completion_price: float | None = None

    @property
    def context_label(self) -> str:
        """Return the context window as a short human string."""
        if self.context_length is None:
            return ""
        if self.context_length >= _MILLION:
            return f"{self.context_length / _MILLION:.0f}M context"
        if self.context_length >= _THOUSAND:
            return f"{self.context_length / _THOUSAND:.0f}K context"
        return f"{self.context_length} context"

    @property
    def price_label(self) -> str:
        """Return the prompt and completion price per million tokens."""
        prices = [
            price
            for price in (self.prompt_price, self.completion_price)
            if price is not None
        ]
        if not prices:
            return ""
        if not any(prices):
            return "free"
        rates = " / ".join(f"${price * _MILLION:.2f}" for price in prices)
        return f"{rates} per M"

    def matches(self, query: str) -> bool:
        """Return whether this model matches a search query.

        Every whitespace-separated term has to appear somewhere in the id, the
        name, or the description, so "gemini flash" narrows rather than widens.

        Args:
            query: The user's raw search text.

        Returns:
            ``True`` when the model should stay in the filtered list.
        """
        terms = query.lower().split()
        if not terms:
            return True
        haystack = f"{self.id} {self.name} {self.description}".lower()
        return all(term in haystack for term in terms)


def thinking_token_headroom(level: ThinkingLevel) -> int:
    """Return how many output tokens this level needs on top of the answer.

    Every provider here draws reasoning tokens from the same output allowance
    as the answer, so a model told to think hard inside a 2048-token budget can
    spend the lot thinking and return nothing. Callers add this to the user's
    limit instead of asking them to reason about the interaction.

    Args:
        level: The level the user chose.

    Returns:
        Extra output tokens to allow; 0 when thinking is off.
    """
    budget = _GEMINI_BUDGETS[level]
    # "Auto" has no stated budget; give it the same room as MEDIUM.
    return _GEMINI_BUDGETS[ThinkingLevel.MEDIUM] if budget < 0 else budget


def supported_thinking_levels(
    provider: Provider, *, supports_thinking: bool = True
) -> tuple[ThinkingLevel, ...]:
    """Return the thinking levels worth offering for a provider and model.

    Args:
        provider: The selected provider.
        supports_thinking: Whether the selected model reasons at all. A model
            that does not gets only :attr:`ThinkingLevel.OFF`, so the UI can
            show the control disabled rather than hide it and leave the user
            wondering where it went.

    Returns:
        The levels in increasing order of effort.
    """
    if not supports_thinking:
        return (ThinkingLevel.OFF,)
    if provider is Provider.GEMINI:
        return _GEMINI_LEVELS
    return _EFFORT_LEVELS


def thinking_payload(
    provider: Provider, level: ThinkingLevel, *, supports_thinking: bool = True
) -> dict[str, Any]:
    """Return the request fields that ask for this much reasoning.

    Args:
        provider: The provider the request is going to.
        level: The level the user chose.
        supports_thinking: Whether the model reasons at all. When it does not
            no reasoning field is sent: providers reject the parameter outright
            on a model that has no reasoning to configure.

    Returns:
        Fields to merge into the request body; empty when there is nothing to
        say.
    """
    if not supports_thinking:
        return {}

    if provider is Provider.GEMINI:
        return {"thinkingConfig": {"thinkingBudget": _GEMINI_BUDGETS[level]}}

    if provider is Provider.OPENROUTER:
        if level is ThinkingLevel.OFF:
            return {"reasoning": {"enabled": False}}
        # `exclude` keeps the reasoning trace out of the reply: the app parses
        # the answer as JSON and never shows the thinking.
        return {"reasoning": {"effort": level.value, "exclude": True}}

    return {"reasoning_effort": "none" if level is ThinkingLevel.OFF else level.value}
