"""Tests for the chat-model factory."""

from unittest.mock import patch

import pytest
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from practice_core.providers import Provider
from pydantic import SecretStr

from practice_runtime.errors import ConfigurationError
from practice_runtime.llm import (
    _create_gemini,
    _create_openrouter,
    get_llm,
)
from practice_runtime.settings import (
    GeminiSettings,
    LLMSettings,
    OpenRouterSettings,
    ProviderSettings,
)


def _config(
    provider: Provider = Provider.GEMINI, model: str | None = None
) -> LLMSettings:
    """Build LLM settings for the given provider."""
    return LLMSettings(
        provider=provider, model=model, request_timeout=12.5, max_retries=3
    )


def _gemini(key: str | None = "test-key", proxy: str | None = None) -> ProviderSettings:
    return GeminiSettings(api_key=SecretStr(key) if key else None, proxy=proxy)


def _openrouter(
    key: str | None = "test-key", proxy: str | None = None
) -> ProviderSettings:
    return OpenRouterSettings(api_key=SecretStr(key) if key else None, proxy=proxy)


class TestGetLLM:
    """Tests for provider dispatch."""

    def test_gemini_provider(self) -> None:
        assert isinstance(get_llm(_config(), _gemini()), ChatGoogleGenerativeAI)

    def test_openrouter_provider(self) -> None:
        llm = get_llm(_config(Provider.OPENROUTER, "openai/gpt-4o-mini"), _openrouter())
        assert isinstance(llm, ChatOpenAI)
        assert llm.model_name == "openai/gpt-4o-mini"

    @pytest.mark.parametrize("provider", ["unknown", "dashscope", "google"])
    def test_invalid_provider_is_rejected_by_settings(self, provider: str) -> None:
        """An unknown provider cannot be constructed, so dispatch stays total."""
        with pytest.raises(ValueError, match="provider"):
            LLMSettings.model_validate({"provider": provider})


class TestCreateGemini:
    """Tests for the Gemini client."""

    def test_missing_api_key(self) -> None:
        with pytest.raises(ConfigurationError, match="GEMINI_API_KEY is not set"):
            _create_gemini(_config(), _gemini(key=None))

    def test_uses_the_providers_default_model(self) -> None:
        with patch("practice_runtime.llm.ChatGoogleGenerativeAI") as chat_model:
            _create_gemini(_config(), _gemini())

        assert chat_model.call_args.kwargs["model"] == "gemini-2.5-flash-lite"

    def test_returns_generative_ai(self) -> None:
        assert isinstance(_create_gemini(_config(), _gemini()), ChatGoogleGenerativeAI)

    def test_with_proxy(self) -> None:
        with patch("practice_runtime.llm.ChatGoogleGenerativeAI") as chat_model:
            _create_gemini(_config(), _gemini(proxy="http://proxy:8080"))

        assert chat_model.call_args.kwargs["client_args"] == {
            "proxy": "http://proxy:8080"
        }

    def test_without_proxy_passes_no_client_args(self) -> None:
        with patch("practice_runtime.llm.ChatGoogleGenerativeAI") as chat_model:
            _create_gemini(_config(), _gemini())

        assert "client_args" not in chat_model.call_args.kwargs


class TestCreateOpenRouter:
    """Tests for the OpenRouter client."""

    def test_missing_api_key(self) -> None:
        with pytest.raises(ConfigurationError, match="OPENROUTER_API_KEY is not set"):
            _create_openrouter(_config(Provider.OPENROUTER), _openrouter(key=None))

    def test_blank_api_key_counts_as_unset(self) -> None:
        with pytest.raises(ConfigurationError, match="OPENROUTER_API_KEY is not set"):
            _create_openrouter(_config(Provider.OPENROUTER), _openrouter(key="   "))

    def test_returns_chat_openai(self) -> None:
        llm = _create_openrouter(_config(Provider.OPENROUTER), _openrouter())
        assert isinstance(llm, ChatOpenAI)
        assert llm.model_name == "google/gemma-4-26b-a4b-it"

    def test_applies_timeout_and_retries(self) -> None:
        llm = _create_openrouter(_config(Provider.OPENROUTER), _openrouter())
        assert llm.request_timeout == 12.5
        assert llm.max_retries == 3

    def test_with_proxy(self) -> None:
        with patch("practice_runtime.llm.ChatOpenAI") as chat_model:
            _create_openrouter(
                _config(Provider.OPENROUTER), _openrouter(proxy="http://proxy:8080")
            )

        assert chat_model.call_args.kwargs["openai_proxy"] == "http://proxy:8080"

    def test_without_proxy_passes_none(self) -> None:
        with patch("practice_runtime.llm.ChatOpenAI") as chat_model:
            _create_openrouter(_config(Provider.OPENROUTER), _openrouter())

        assert "openai_proxy" not in chat_model.call_args.kwargs
