"""Gemini LLM provider."""

from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import SecretStr

from config.settings import settings
from src.english_practice.llm.base import BaseLLM


class GeminiLLM(BaseLLM):
    """Gemini LLM provider."""

    THINKING_LEVEL_MODELS = {
        "gemini-3.1-pro",
        "gemini-3-pro",
        "gemini-3-flash",
    }

    def _supports_thinking_level(self, model: str) -> bool:
        """Check if model supports thinking_level (Gemini 3+ only)."""
        return any(m in model for m in self.THINKING_LEVEL_MODELS)

    def create(self) -> ChatGoogleGenerativeAI:
        """Create Gemini LLM client with optional proxy support."""
        if not settings.gemini.api_key:
            raise ValueError("GEMINI_API_KEY not set. Please add it to your .env file.")

        kwargs: dict[str, Any] = {
            "model": settings.gemini.model,
            "google_api_key": SecretStr(settings.gemini.api_key),
            "temperature": settings.gemini.temperature,
            "max_output_tokens": settings.gemini.max_tokens,
            "top_p": settings.gemini.top_p,
        }

        if settings.gemini.proxy:
            kwargs["client_args"] = {"proxy": settings.gemini.proxy}

        if settings.gemini.thinking_level and self._supports_thinking_level(
            settings.gemini.model
        ):
            kwargs["thinking_level"] = settings.gemini.thinking_level

        return ChatGoogleGenerativeAI(**kwargs)
