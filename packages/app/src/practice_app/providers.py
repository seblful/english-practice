"""Providers, thinking levels, and the request fragments they translate into."""

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
    def short_label(self) -> str:
        """Return the name to use where a phone has one line to spare."""
        return _SHORT_LABELS[self]

    @property
    def console_url(self) -> str:
        """Return the page where a user creates an API key."""
        return _CONSOLE_URLS[self]

    @property
    def default_model(self) -> str:
        """Return the model to start from before the user picks one."""
        return _DEFAULT_MODELS[self]

    @property
    def default_model_reasons(self) -> bool:
        """Whether :attr:`default_model` has a thinking control to offer."""
        return _DEFAULT_MODEL_REASONS[self]

    @property
    def default_thinking(self) -> "ThinkingLevel":
        """Return the thinking level a fresh install grades at."""
        return ThinkingLevel.LOW if self.default_model_reasons else ThinkingLevel.OFF

    @property
    def superseded_models(self) -> frozenset[str]:
        """Return the models this provider's current default has replaced."""
        return _SUPERSEDED_MODELS[self]

    @property
    def lists_models_anonymously(self) -> bool:
        """Whether the model catalogue can be fetched without an API key."""
        return self is Provider.OPENROUTER


_PROVIDER_LABELS: Final[dict[Provider, str]] = {
    Provider.OPENROUTER: "OpenRouter",
    Provider.GEMINI: "Google Gemini",
    Provider.OPENAI: "OpenAI",
}

# The short name: "Google Gemini" does not fit a third of a 360dp screen.
_SHORT_LABELS: Final[dict[Provider, str]] = {
    Provider.OPENROUTER: "OpenRouter",
    Provider.GEMINI: "Gemini",
    Provider.OPENAI: "OpenAI",
}

_CONSOLE_URLS: Final[dict[Provider, str]] = {
    Provider.OPENROUTER: "https://openrouter.ai/keys",
    Provider.GEMINI: "https://aistudio.google.com/apikey",
    Provider.OPENAI: "https://platform.openai.com/api-keys",
}

# Every exercise is a picture, so vision is not optional; a flagship is waste.
_DEFAULT_MODELS: Final[dict[Provider, str]] = {
    Provider.OPENROUTER: "google/gemini-3.8-flash",
    Provider.GEMINI: "gemini-3.8-flash",
    # The balanced tier of the GPT-5.6 series, between Luna and Sol.
    Provider.OPENAI: "gpt-5.6-terra",
}

# All three reason, so the thinking control is offered rather than greyed out.
_DEFAULT_MODEL_REASONS: Final[dict[Provider, bool]] = dict.fromkeys(Provider, True)

# A stored model that is still one of these is a default left behind, not a choice.
_SUPERSEDED_MODELS: Final[dict[Provider, frozenset[str]]] = {
    Provider.OPENROUTER: frozenset({"google/gemini-2.5-flash"}),
    Provider.GEMINI: frozenset({"gemini-2.5-flash"}),
    Provider.OPENAI: frozenset({"gpt-4.1-mini"}),
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

# Gemini takes a budget: 0 disables, -1 defers to the model, the rest are caps.
_GEMINI_BUDGETS: Final[dict[ThinkingLevel, int]] = {
    ThinkingLevel.OFF: 0,
    ThinkingLevel.MINIMAL: 512,
    ThinkingLevel.LOW: 2048,
    ThinkingLevel.MEDIUM: 8192,
    ThinkingLevel.HIGH: 24576,
    ThinkingLevel.DYNAMIC: -1,
}

# OpenAI's named efforts; "Auto" is omission, which is what OFF already does.
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
    """One entry of a provider's model catalogue."""

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
        """Return whether this model matches a search query."""
        terms = query.lower().split()
        if not terms:
            return True
        haystack = f"{self.id} {self.name} {self.description}".lower()
        return all(term in haystack for term in terms)


def thinking_token_headroom(level: ThinkingLevel) -> int:
    """Return how many output tokens this level needs on top of the answer."""
    budget = _GEMINI_BUDGETS[level]
    # "Auto" has no stated budget; give it the same room as MEDIUM.
    return _GEMINI_BUDGETS[ThinkingLevel.MEDIUM] if budget < 0 else budget


def supported_thinking_levels(
    provider: Provider, *, supports_thinking: bool = True
) -> tuple[ThinkingLevel, ...]:
    """Return the thinking levels worth offering for a provider and model."""
    if not supports_thinking:
        return (ThinkingLevel.OFF,)
    if provider is Provider.GEMINI:
        return _GEMINI_LEVELS
    return _EFFORT_LEVELS


def thinking_payload(
    provider: Provider, level: ThinkingLevel, *, supports_thinking: bool = True
) -> dict[str, Any]:
    """Return the request fields that ask for this much reasoning."""
    if not supports_thinking:
        return {}

    if provider is Provider.GEMINI:
        return {"thinkingConfig": {"thinkingBudget": _GEMINI_BUDGETS[level]}}

    if provider is Provider.OPENROUTER:
        if level is ThinkingLevel.OFF:
            return {"reasoning": {"enabled": False}}
        # `exclude` keeps the reasoning trace out of a reply the app parses as JSON.
        return {"reasoning": {"effort": level.value, "exclude": True}}

    return {"reasoning_effort": "none" if level is ThinkingLevel.OFF else level.value}
