"""Tests for the chat-model factory."""

import pytest
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from english_practice.errors import ConfigurationError
from english_practice.llm import (
    _create_dashscope,
    _create_gemini,
    _create_openrouter,
    get_llm,
)
from english_practice.settings import (
    DashscopeSettings,
    GeminiSettings,
    LLMProvider,
    LLMSettings,
    OpenRouterSettings,
    Settings,
)


def _config(
    provider: LLMProvider = "dashscope", key: str | None = "test-key"
) -> LLMSettings:
    """Build LLM settings with the given provider keyed and ready."""
    secret = SecretStr(key) if key is not None else None
    return LLMSettings(
        provider=provider,
        request_timeout=12.5,
        max_retries=3,
        dashscope=DashscopeSettings(api_key=secret, model="qwen3-vl-flash"),
        gemini=GeminiSettings(api_key=secret, model="gemini-2.5-flash"),
        openrouter=OpenRouterSettings(api_key=secret, model="openai/gpt-4o-mini"),
    )


class TestGetLLM:
    """Tests for provider dispatch."""

    def test_dashscope_provider(self) -> None:
        llm = get_llm(_config("dashscope"))
        assert isinstance(llm, ChatOpenAI)
        assert llm.model_name == "qwen3-vl-flash"

    def test_gemini_provider(self) -> None:
        assert isinstance(get_llm(_config("gemini")), ChatGoogleGenerativeAI)

    def test_openrouter_provider(self) -> None:
        llm = get_llm(_config("openrouter"))
        assert isinstance(llm, ChatOpenAI)
        assert llm.model_name == "openai/gpt-4o-mini"

    def test_defaults_to_application_settings(self, monkeypatch) -> None:
        """With no argument the factory reads the application settings."""
        settings = Settings(llm=_config("openrouter"))
        monkeypatch.setattr("english_practice.llm.get_settings", lambda: settings)

        assert isinstance(get_llm(), ChatOpenAI)

    def test_invalid_provider_is_rejected_by_settings(self) -> None:
        """An unknown provider cannot be constructed, so dispatch stays total."""
        with pytest.raises(ValueError, match="provider"):
            LLMSettings.model_validate({"provider": "unknown"})


class TestCreateDashscope:
    """Tests for the DashScope client."""

    def test_missing_api_key(self) -> None:
        with pytest.raises(ConfigurationError, match="DASHSCOPE_API_KEY is not set"):
            _create_dashscope(_config(key=None))

    def test_blank_api_key_counts_as_unset(self) -> None:
        with pytest.raises(ConfigurationError, match="DASHSCOPE_API_KEY is not set"):
            _create_dashscope(_config(key="   "))

    def test_applies_timeout_and_retries(self) -> None:
        llm = _create_dashscope(_config())
        assert llm.request_timeout == 12.5
        assert llm.max_retries == 3


class TestCreateGemini:
    """Tests for the Gemini client."""

    def test_missing_api_key(self) -> None:
        with pytest.raises(ConfigurationError, match="GEMINI_API_KEY is not set"):
            _create_gemini(_config(key=None))

    def test_returns_generative_ai(self) -> None:
        assert isinstance(_create_gemini(_config()), ChatGoogleGenerativeAI)

    def test_with_proxy(self) -> None:
        config = _config()
        config.gemini.proxy = "http://proxy:8080"

        assert _create_gemini(config) is not None


class TestCreateOpenRouter:
    """Tests for the OpenRouter client."""

    def test_missing_api_key(self) -> None:
        with pytest.raises(ConfigurationError, match="OPENROUTER_API_KEY is not set"):
            _create_openrouter(_config(key=None))

    def test_returns_chat_openai(self) -> None:
        assert isinstance(_create_openrouter(_config()), ChatOpenAI)
