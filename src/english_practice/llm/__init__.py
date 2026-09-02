"""Chat-model factory.

One function per provider, selected by :func:`get_llm`. Clients are *not*
cached here: each one owns an HTTP connection pool, so its lifetime is the
caller's business — the bot builds a single :class:`~english_practice.services
.agent_service.AgentService` for the whole process and the agents hold onto
their client from there.
"""

from typing import Any, assert_never

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from english_practice.errors import ConfigurationError
from english_practice.settings import LLMSettings, get_settings, secret_value

__all__ = ["get_llm"]


def _require_key(key: SecretStr | None, env_var: str) -> SecretStr:
    """Return the API key, or explain which variable has to be set.

    Args:
        key: The configured key, if any.
        env_var: Name of the environment variable that supplies it.

    Returns:
        The key, guaranteed non-blank.

    Raises:
        ConfigurationError: If the key is unset or blank.
    """
    value = secret_value(key)
    if value is None:
        raise ConfigurationError(f"{env_var} is not set")
    return SecretStr(value)


def _create_dashscope(config: LLMSettings) -> ChatOpenAI:
    """Create a DashScope client through its OpenAI-compatible endpoint."""
    provider = config.dashscope
    return ChatOpenAI(
        model=provider.model,
        api_key=_require_key(provider.api_key, "DASHSCOPE_API_KEY"),
        base_url=provider.base_url,
        temperature=provider.temperature,
        max_tokens=provider.max_tokens,
        timeout=config.request_timeout,
        max_retries=config.max_retries,
    )


def _create_gemini(config: LLMSettings) -> ChatGoogleGenerativeAI:
    """Create a Google Gemini client."""
    provider = config.gemini
    kwargs: dict[str, Any] = {
        "model": provider.model,
        "google_api_key": _require_key(provider.api_key, "GEMINI_API_KEY"),
        "temperature": provider.temperature,
        "max_output_tokens": provider.max_tokens,
        "top_p": provider.top_p,
        "timeout": config.request_timeout,
        "max_retries": config.max_retries,
    }

    if provider.proxy:
        kwargs["client_args"] = {"proxy": provider.proxy}

    return ChatGoogleGenerativeAI(**kwargs)


def _create_openrouter(config: LLMSettings) -> ChatOpenAI:
    """Create an OpenRouter client."""
    provider = config.openrouter
    return ChatOpenAI(
        model=provider.model,
        api_key=_require_key(provider.api_key, "OPENROUTER_API_KEY"),
        base_url=provider.base_url,
        temperature=provider.temperature,
        max_tokens=provider.max_tokens,
        timeout=config.request_timeout,
        max_retries=config.max_retries,
    )


def get_llm(config: LLMSettings | None = None) -> BaseChatModel:
    """Create a chat model for the configured provider.

    Args:
        config: LLM settings to build from. Defaults to the application's.

    Returns:
        A ready chat model with the provider's timeout and retry policy applied.

    Raises:
        ConfigurationError: If the selected provider has no API key.
    """
    config = config or get_settings().llm

    match config.provider:
        case "dashscope":
            return _create_dashscope(config)
        case "gemini":
            return _create_gemini(config)
        case "openrouter":
            return _create_openrouter(config)
        case unreachable:  # pragma: no cover - the Literal is validated upstream
            assert_never(unreachable)
