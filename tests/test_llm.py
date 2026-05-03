"""Tests for LLM provider factory."""

from unittest.mock import patch

import pytest

from src.english_practice.llm import get_llm


class TestGetLLM:
    """Tests for get_llm factory."""

    @patch("src.english_practice.llm._create_dashscope")
    def test_dashscope_provider(self, mock_create) -> None:
        with patch("src.english_practice.llm.settings") as mock_settings:
            mock_settings.llm.provider = "dashscope"
            get_llm()
            mock_create.assert_called_once()

    @patch("src.english_practice.llm._create_gemini")
    def test_gemini_provider(self, mock_create) -> None:
        with patch("src.english_practice.llm.settings") as mock_settings:
            mock_settings.llm.provider = "gemini"
            get_llm()
            mock_create.assert_called_once()

    @patch("src.english_practice.llm._create_openrouter")
    def test_openrouter_provider(self, mock_create) -> None:
        with patch("src.english_practice.llm.settings") as mock_settings:
            mock_settings.llm.provider = "openrouter"
            get_llm()
            mock_create.assert_called_once()

    def test_unknown_provider(self) -> None:
        with patch("src.english_practice.llm.settings") as mock_settings:
            mock_settings.llm.provider = "unknown"
            with pytest.raises(ValueError, match="Unknown LLM provider"):
                get_llm()


class TestCreateDashscope:
    """Tests for _create_dashscope."""

    def test_missing_api_key(self) -> None:
        with patch("src.english_practice.llm.settings") as mock_settings:
            mock_settings.llm.dashscope.api_key = None
            mock_settings.llm.provider = "dashscope"
            with pytest.raises(ValueError, match="DASHSCOPE_API_KEY not set"):
                from src.english_practice.llm import _create_dashscope
                _create_dashscope()

    def test_returns_chat_openai(self) -> None:
        with patch("src.english_practice.llm.settings") as mock_settings:
            mock_settings.llm.dashscope.api_key = "test-key"
            mock_settings.llm.dashscope.model = "qwen3-vl-flash"
            mock_settings.llm.dashscope.base_url = "https://dashscope.intl.com"
            mock_settings.llm.dashscope.temperature = 0.7
            mock_settings.llm.dashscope.max_tokens = 2048
            from src.english_practice.llm import _create_dashscope
            from langchain_openai import ChatOpenAI
            result = _create_dashscope()
            assert isinstance(result, ChatOpenAI)
            assert result.model_name == "qwen3-vl-flash"


class TestCreateGemini:
    """Tests for _create_gemini."""

    def test_missing_api_key(self) -> None:
        with patch("src.english_practice.llm.settings") as mock_settings:
            mock_settings.llm.gemini.api_key = None
            mock_settings.llm.gemini.proxy = None
            with pytest.raises(ValueError, match="GEMINI_API_KEY not set"):
                from src.english_practice.llm import _create_gemini
                _create_gemini()

    def test_returns_generative_ai(self) -> None:
        with patch("src.english_practice.llm.settings") as mock_settings:
            mock_settings.llm.gemini.api_key = "test-key"
            mock_settings.llm.gemini.model = "gemini-2.5-flash"
            mock_settings.llm.gemini.temperature = 0.7
            mock_settings.llm.gemini.max_tokens = 2048
            mock_settings.llm.gemini.top_p = 0.95
            mock_settings.llm.gemini.proxy = None
            from src.english_practice.llm import _create_gemini
            from langchain_google_genai import ChatGoogleGenerativeAI
            result = _create_gemini()
            assert isinstance(result, ChatGoogleGenerativeAI)

    def test_with_proxy(self) -> None:
        with patch("src.english_practice.llm.settings") as mock_settings:
            mock_settings.llm.gemini.api_key = "test-key"
            mock_settings.llm.gemini.model = "gemini-2.5-flash"
            mock_settings.llm.gemini.temperature = 0.7
            mock_settings.llm.gemini.max_tokens = 2048
            mock_settings.llm.gemini.top_p = 0.95
            mock_settings.llm.gemini.proxy = "http://proxy:8080"
            from src.english_practice.llm import _create_gemini
            result = _create_gemini()
            # Should not raise when proxy is set
            assert result is not None


class TestCreateOpenRouter:
    """Tests for _create_openrouter."""

    def test_missing_api_key(self) -> None:
        with patch("src.english_practice.llm.settings") as mock_settings:
            mock_settings.llm.openrouter.api_key = None
            with pytest.raises(ValueError, match="OPENROUTER_API_KEY not set"):
                from src.english_practice.llm import _create_openrouter
                _create_openrouter()

    def test_returns_chat_openai(self) -> None:
        with patch("src.english_practice.llm.settings") as mock_settings:
            mock_settings.llm.openrouter.api_key = "test-key"
            mock_settings.llm.openrouter.model = "openai/gpt-4o-mini"
            mock_settings.llm.openrouter.base_url = "https://openrouter.ai"
            mock_settings.llm.openrouter.temperature = 0.7
            mock_settings.llm.openrouter.max_tokens = 2048
            from src.english_practice.llm import _create_openrouter
            from langchain_openai import ChatOpenAI
            result = _create_openrouter()
            assert isinstance(result, ChatOpenAI)
            assert result.model_name == "openai/gpt-4o-mini"
