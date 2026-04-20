"""OpenRouter LLM provider (OpenAI-compatible API)."""

from pydantic import SecretStr
from langchain_openai import ChatOpenAI

from config.settings import settings
from src.english_practice.llm.base import BaseLLM


class OpenRouterLLM(BaseLLM):
    """OpenRouter LLM provider (OpenAI-compatible API)."""

    def create(self) -> ChatOpenAI:
        """Create OpenRouter LLM client."""
        if not settings.llm.openrouter.api_key:
            raise ValueError(
                "OPENROUTER_API_KEY not set. Please add it to your .env file."
            )
        return ChatOpenAI(
            model=settings.llm.openrouter.model,
            api_key=SecretStr(settings.llm.openrouter.api_key),
            base_url=settings.llm.openrouter.base_url,
            temperature=settings.llm.openrouter.temperature,
            max_tokens=settings.llm.openrouter.max_tokens,
        )
