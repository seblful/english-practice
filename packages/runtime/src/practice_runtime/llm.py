"""Chat-model factory."""

from typing import Any, Final

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from practice_core.providers import Provider
from pydantic import SecretStr

from practice_runtime.errors import ConfigurationError
from practice_runtime.settings import LLMSettings, ProviderSettings

__all__ = ["get_llm"]

#: OpenRouter's OpenAI-compatible chat endpoint.
_OPENROUTER_CHAT_URL: Final = "https://openrouter.ai/api/v1"


def _require_key(credentials: ProviderSettings) -> SecretStr:
    """Return the API key, or explain which variable has to be set."""
    key = credentials.key
    if key is None:
        raise ConfigurationError(f"{credentials.key_variable} is not set")
    return SecretStr(key)


def _create_gemini(
    config: LLMSettings, credentials: ProviderSettings
) -> ChatGoogleGenerativeAI:
    """Create a Google Gemini client."""
    kwargs: dict[str, Any] = {
        "model": config.active_model,
        "google_api_key": _require_key(credentials),
        "temperature": config.temperature,
        "max_output_tokens": config.max_tokens,
        "top_p": config.top_p,
        "timeout": config.request_timeout,
        "max_retries": config.max_retries,
    }

    if credentials.proxy:
        kwargs["client_args"] = {"proxy": credentials.proxy}

    return ChatGoogleGenerativeAI(**kwargs)


def _create_openrouter(
    config: LLMSettings, credentials: ProviderSettings
) -> ChatOpenAI:
    """Create an OpenRouter client."""
    kwargs: dict[str, Any] = {
        "model": config.active_model,
        "api_key": _require_key(credentials),
        "base_url": _OPENROUTER_CHAT_URL,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "top_p": config.top_p,
        "timeout": config.request_timeout,
        "max_retries": config.max_retries,
    }

    if credentials.proxy:
        kwargs["openai_proxy"] = credentials.proxy

    return ChatOpenAI(**kwargs)


def get_llm(config: LLMSettings, credentials: ProviderSettings) -> BaseChatModel:
    """Create a chat model for the configured provider, with its credentials."""
    if config.provider is Provider.OPENROUTER:
        return _create_openrouter(config, credentials)
    return _create_gemini(config, credentials)
