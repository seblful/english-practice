"""The services a model is reached through, and what each needs."""

from enum import StrEnum
from typing import Final

__all__ = ["DEFAULT_PROVIDER", "Provider"]


class Provider(StrEnum):
    """A model service: whose key a request carries, and where it is sent."""

    GEMINI = "gemini"
    OPENROUTER = "openrouter"

    @property
    def label(self) -> str:
        """Return the service's name as its own docs write it."""
        return _LABELS[self]

    @property
    def key_url(self) -> str:
        """Return the page where a user creates an API key."""
        return _KEY_URLS[self]

    @property
    def key_variable(self) -> str:
        """Return the environment variable a server reads this key from."""
        return f"{self.upper()}_API_KEY"

    @property
    def decision_url(self) -> str:
        """Return the endpoint that answers decision requests."""
        return _DECISION_URLS[self]

    @property
    def decision_model(self) -> str:
        """Return Gemini Decision 1 under the id this provider knows it by."""
        return _DECISION_MODELS[self]

    def headers(self, api_key: str) -> dict[str, str]:
        """Return the auth and content headers for a request with this key."""
        headers = {"Content-Type": "application/json"}
        # A key pasted with a stray newline builds an illegal header value.
        key = api_key.strip()
        if key:
            if self is Provider.OPENROUTER:
                headers["Authorization"] = f"Bearer {key}"
            else:
                headers["x-goog-api-key"] = key
        return headers


_LABELS: Final = {
    Provider.GEMINI: "Google AI Studio",
    Provider.OPENROUTER: "OpenRouter",
}
_KEY_URLS: Final = {
    Provider.GEMINI: "https://aistudio.google.com/apikey",
    Provider.OPENROUTER: "https://openrouter.ai/keys",
}
_DECISION_URLS: Final = {
    Provider.GEMINI: "https://generativelanguage.googleapis.com/v1beta/decisions",
    Provider.OPENROUTER: "https://openrouter.ai/api/alpha/decisions",
}
# Gemini Decision 1 reads text, images, audio, video and PDF through both.
_DECISION_MODELS: Final = {
    Provider.GEMINI: "gemini-decision-1",
    Provider.OPENROUTER: "google/gemini-decision-1",
}

#: What a fresh install, or a server that names none, uses.
# Gemini first: Google's free tier covers practice, and OpenRouter has none.
DEFAULT_PROVIDER: Final = Provider.GEMINI
