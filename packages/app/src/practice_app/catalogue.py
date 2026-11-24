"""The decision models the user can pick from, and how each provider lists them."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import Any, Final

from practice_core.providers import Provider

__all__ = [
    "ModelInfo",
    "default_model_info",
    "is_decision_model",
    "parse_models",
]

_MARKER: Final = "decision"
# Google documents image input for Gemini Decision; for other ids, no claim.
_KNOWN_VISION_MARKER: Final = "gemini-decision"
_MILLION = 1_000_000
_THOUSAND = 1_000


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """One entry of a provider's decision-model catalogue."""

    id: str
    name: str
    description: str = ""
    context_length: int | None = None
    supports_images: bool = True

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

    def matches(self, query: str) -> bool:
        """Return whether this model matches a search query."""
        terms = query.lower().split()
        if not terms:
            return True
        haystack = f"{self.id} {self.name} {self.description}".lower()
        return all(term in haystack for term in terms)


_GEMINI_DECISION: Final = ModelInfo(
    id="",
    name="Gemini Decision 1",
    description=(
        "Google's decision model: calibrated yes/no answers over text, images, "
        "video, audio and PDF."
    ),
)


def default_model_info(provider: Provider) -> ModelInfo:
    """Return the entry always offered on a provider, listed or not."""
    return replace(_GEMINI_DECISION, id=provider.decision_model)


def is_decision_model(model_id: str, methods: Iterable[object] = ()) -> bool:
    """Return whether a model id, or the methods it supports, name a decision model."""
    if _MARKER in model_id.lower():
        return True
    return any(
        isinstance(method, str) and _MARKER in method.lower() for method in methods
    )


def _text(entry: dict[str, Any], key: str) -> str:
    """Return one stripped string field of a listing entry, or empty."""
    value = entry.get(key)
    return value.strip() if isinstance(value, str) else ""


def _count(value: object) -> int | None:
    """Return a token count, or ``None`` for anything that is not one."""
    # bool is an int subclass, and `true` is not a token count.
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _list(value: object) -> list[Any] | None:
    """Return ``value`` when it is a list, else ``None``."""
    return value if isinstance(value, list) else None


def _gemini_entry(entry: object) -> ModelInfo | None:
    """Return one ``GET /v1beta/models`` entry, if it is a decision model."""
    if not isinstance(entry, dict):
        return None
    model_id = _text(entry, "name").removeprefix("models/")
    if not model_id or not is_decision_model(
        model_id, _list(entry.get("supportedGenerationMethods")) or ()
    ):
        return None
    # Google lists no input modalities, and documents images for its decision model.
    return ModelInfo(
        id=model_id,
        name=_text(entry, "displayName") or model_id,
        description=_text(entry, "description"),
        context_length=_count(entry.get("inputTokenLimit")),
    )


def _openrouter_entry(entry: object) -> ModelInfo | None:
    """Return one OpenRouter catalogue entry, if it is a decision model."""
    if not isinstance(entry, dict):
        return None
    model_id = _text(entry, "id")
    if not model_id:
        return None
    architecture = entry.get("architecture")
    architecture = architecture if isinstance(architecture, dict) else {}
    outputs = _list(architecture.get("output_modalities")) or []
    if "decisions" not in outputs and _MARKER not in model_id.lower():
        return None

    inputs = _list(architecture.get("input_modalities"))
    return ModelInfo(
        id=model_id,
        name=_text(entry, "name") or model_id,
        description=_text(entry, "description"),
        context_length=_count(entry.get("context_length")),
        supports_images=(
            "image" in inputs
            if inputs is not None
            else _KNOWN_VISION_MARKER in model_id.lower()
        ),
    )


_READERS: Final[dict[Provider, tuple[str, Callable[[object], ModelInfo | None]]]] = {
    Provider.OPENROUTER: ("data", _openrouter_entry),
    Provider.GEMINI: ("models", _gemini_entry),
}


def parse_models(provider: Provider, payload: object) -> list[ModelInfo]:
    """Return the decision models in a provider's model listing, its default first.

    The default is always present, so the picker is never empty: neither
    listing documents exactly how a decision model appears in it.
    """
    field, read = _READERS[provider]
    entries = payload.get(field) if isinstance(payload, dict) else None
    listed = [model for model in map(read, _list(entries) or []) if model is not None]

    seen: dict[str, ModelInfo] = {}
    for model in sorted(listed, key=lambda model: model.id):
        seen.setdefault(model.id, model)
    default = seen.pop(provider.decision_model, None)
    # Google documents image input for it, which outranks an odd listing.
    default = (
        replace(default, supports_images=True)
        if default is not None
        else default_model_info(provider)
    )
    return [default, *seen.values()]
