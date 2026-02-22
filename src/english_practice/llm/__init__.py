"""LLM providers module."""

from langchain_core.language_models.chat_models import BaseChatModel

from config.settings import settings
from src.english_practice.llm.base import BaseLLM
from src.english_practice.llm.gemini import GeminiLLM
from src.english_practice.llm.qwen import QwenLLM

__all__ = ["get_llm", "BaseLLM", "GeminiLLM", "QwenLLM"]


def get_llm() -> BaseChatModel:
    """Factory function to create LLM based on configured provider."""
    providers: dict[str, type[BaseLLM]] = {
        "qwen": QwenLLM,
        "gemini": GeminiLLM,
    }

    provider_class = providers.get(settings.llm_provider)
    if not provider_class:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")

    return provider_class().create()
