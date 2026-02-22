"""LLM providers for agents."""

from abc import ABC, abstractmethod
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_qwq import ChatQwen
from pydantic import SecretStr

from config.settings import settings


class BaseLLM(ABC):
    """Base class for LLM providers."""

    @abstractmethod
    def create(self) -> BaseChatModel:
        """Create and return the LLM client."""
        pass


class QwenLLM(BaseLLM):
    """Qwen LLM provider (DashScope)."""

    def create(self) -> ChatQwen:
        """Create Qwen LLM client."""
        if not settings.qwen.api_key:
            raise ValueError(
                "DASHSCOPE_API_KEY not set. Please add it to your .env file."
            )
        return ChatQwen(
            model=settings.qwen.model,
            api_key=SecretStr(settings.qwen.api_key),
            base_url=settings.qwen.base_url,
            temperature=settings.qwen.temperature,
            max_tokens=settings.qwen.max_tokens,
        )


class GeminiLLM(BaseLLM):
    """Gemini LLM provider."""

    THINKING_MODELS = {
        "gemini-3.1-pro-preview",
        "gemini-3-pro-preview",
        "gemini-3-flash-preview",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
    }

    def _supports_thinking(self, model: str) -> bool:
        """Check if model supports thinking level."""
        return any(m in model for m in self.THINKING_MODELS)

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

        if settings.gemini.thinking_level and self._supports_thinking(
            settings.gemini.model
        ):
            kwargs["thinking_level"] = settings.gemini.thinking_level

        return ChatGoogleGenerativeAI(**kwargs)


class LocalLLM(BaseLLM):
    """Local OpenAI-compatible LLM provider (llama.cpp, vLLM, etc.)."""

    def create(self) -> ChatOpenAI:
        """Create local OpenAI-compatible LLM client."""
        extra_body: dict[str, Any] = {}
        if settings.local.min_p is not None:
            extra_body["min_p"] = settings.local.min_p
        if settings.local.top_k is not None:
            extra_body["top_k"] = settings.local.top_k

        return ChatOpenAI(
            model=settings.local.model,
            base_url=settings.local.base_url,
            api_key=SecretStr(settings.local.api_key),
            temperature=settings.local.temperature,
            max_tokens=settings.local.max_tokens,
            timeout=settings.local.read_timeout,
            top_p=settings.local.top_p,
            extra_body=extra_body if extra_body else None,
        )


def get_llm() -> BaseChatModel:
    """Factory function to create LLM based on configured provider."""
    providers: dict[str, type[BaseLLM]] = {
        "qwen": QwenLLM,
        "gemini": GeminiLLM,
        "local": LocalLLM,
    }

    provider_class = providers.get(settings.llm_provider)
    if not provider_class:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")

    return provider_class().create()
