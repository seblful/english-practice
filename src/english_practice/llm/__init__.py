"""LLM providers module."""

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from config.settings import settings

__all__ = ["get_llm"]


def _create_dashscope() -> ChatOpenAI:
    """Create DashScope LLM."""
    config = settings.llm.dashscope
    if not config.api_key:
        raise ValueError("DASHSCOPE_API_KEY not set")

    return ChatOpenAI(
        model=config.model,
        api_key=SecretStr(config.api_key),
        base_url=config.base_url,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )


def _create_gemini() -> ChatGoogleGenerativeAI:
    """Create Gemini LLM."""
    config = settings.llm.gemini
    if not config.api_key:
        raise ValueError("GEMINI_API_KEY not set")

    kwargs: dict[str, Any] = {
        "model": config.model,
        "google_api_key": SecretStr(config.api_key),
        "temperature": config.temperature,
        "max_output_tokens": config.max_tokens,
        "top_p": config.top_p,
    }

    if config.proxy:
        kwargs["client_args"] = {"proxy": config.proxy}

    return ChatGoogleGenerativeAI(**kwargs)


def _create_openrouter() -> ChatOpenAI:
    """Create OpenRouter LLM."""
    config = settings.llm.openrouter
    if not config.api_key:
        raise ValueError("OPENROUTER_API_KEY not set")

    return ChatOpenAI(
        model=config.model,
        api_key=SecretStr(config.api_key),
        base_url=config.base_url,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )


def get_llm() -> BaseChatModel:
    """Factory function to create LLM based on configured provider."""
    providers = {
        "dashscope": _create_dashscope,
        "gemini": _create_gemini,
        "openrouter": _create_openrouter,
    }

    provider = settings.llm.provider
    if provider not in providers:
        raise ValueError(f"Unknown LLM provider: {provider}")

    return providers[provider]()
