"""LLM providers module."""

from langchain_core.language_models.chat_models import BaseChatModel

from config.settings import settings
from src.english_practice.llm.base import BaseLLM
from src.english_practice.llm.dashscope import DashscopeLLM
from src.english_practice.llm.gemini import GeminiLLM
from src.english_practice.llm.openrouter import OpenRouterLLM

__all__ = ["get_llm", "BaseLLM", "GeminiLLM", "DashscopeLLM", "OpenRouterLLM"]


def get_llm() -> BaseChatModel:
    """Factory function to create LLM based on configured provider."""
    providers: dict[str, type[BaseLLM]] = {
        "dashscope": DashscopeLLM,
        "gemini": GeminiLLM,
        "openrouter": OpenRouterLLM,
    }

    provider_class = providers.get(settings.llm.provider)
    if not provider_class:
        raise ValueError(f"Unknown LLM provider: {settings.llm.provider}")

    return provider_class().create()
