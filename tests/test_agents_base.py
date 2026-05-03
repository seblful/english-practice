"""Tests for BaseAgent."""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from src.english_practice.agents.base import BaseAgent, _get_prompt_env


class DummyModel(BaseModel):
    name: str


class _TestAgent(BaseAgent):
    """Concrete agent for testing (not collected by pytest)."""
    PROMPT_TEMPLATE = "evaluate.j2"


class TestGetPromptEnv:
    """Tests for _get_prompt_env."""

    def test_returns_jinja_environment(self) -> None:
        env = _get_prompt_env()
        assert env is not None
        # Singleton
        assert _get_prompt_env() is env


class TestBaseAgentRender:
    """Tests for render method."""

    def test_render_returns_string(self) -> None:
        agent = _TestAgent()
        result = agent.render(DummyModel(name="test"))
        assert isinstance(result, str)

    def test_render_uses_template(self) -> None:
        agent = _TestAgent()
        result = agent.render(DummyModel(name="test"))
        assert len(result) > 0


class TestBaseAgentEncodeImage:
    """Tests for _encode_image_sync."""

    def test_encodes_bytes_to_base64(self) -> None:
        agent = _TestAgent()
        result = agent._encode_image_sync(b"hello")
        expected = base64.b64encode(b"hello").decode("utf-8")
        assert result == expected

    def test_empty_bytes(self) -> None:
        agent = _TestAgent()
        result = agent._encode_image_sync(b"")
        assert result == ""


class TestBaseAgentCreateMessage:
    """Tests for _create_message."""

    @pytest.mark.asyncio
    async def test_without_image(self) -> None:
        agent = _TestAgent()
        msg = await agent._create_message("hello")
        assert isinstance(msg, HumanMessage)
        assert msg.content[0]["text"] == "hello"
        assert len(msg.content) == 1

    @pytest.mark.asyncio
    async def test_with_image(self) -> None:
        agent = _TestAgent()
        msg = await agent._create_message("hello", image_data=b"fake_img")
        assert isinstance(msg, HumanMessage)
        assert len(msg.content) == 2
        assert msg.content[0]["text"] == "hello"
        assert msg.content[1]["type"] == "image_url"
        assert "data:image/png;base64," in msg.content[1]["image_url"]["url"]

    @pytest.mark.asyncio
    async def test_with_custom_mime_type(self) -> None:
        agent = _TestAgent()
        msg = await agent._create_message("hello", image_data=b"img", mime_type="image/jpeg")
        assert "data:image/jpeg;base64," in msg.content[1]["image_url"]["url"]


class TestBaseAgentInvokeStructured:
    """Tests for invoke_structured."""

    @pytest.mark.asyncio
    async def test_invokes_llm_and_returns_structured_output(self) -> None:
        agent = _TestAgent()

        # Mock the LLM
        mock_llm = MagicMock()
        mock_structured = MagicMock()
        mock_structured.ainvoke = AsyncMock(
            return_value=DummyModel(name="response")
        )
        mock_llm.with_structured_output = MagicMock(return_value=mock_structured)
        agent._llm = mock_llm

        result = await agent.invoke_structured(
            prompt="test",
            output_model=DummyModel,
            image_data=b"img",
        )

        assert isinstance(result, DummyModel)
        assert result.name == "response"
        mock_llm.with_structured_output.assert_called_once_with(DummyModel)
        mock_structured.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_invoke_without_image(self) -> None:
        agent = _TestAgent()
        mock_llm = MagicMock()
        mock_structured = MagicMock()
        mock_structured.ainvoke = AsyncMock(return_value=DummyModel(name="no img"))
        mock_llm.with_structured_output = MagicMock(return_value=mock_structured)
        agent._llm = mock_llm

        result = await agent.invoke_structured(
            prompt="test",
            output_model=DummyModel,
        )

        assert result.name == "no img"


class TestBaseAgentLLMProperty:
    """Tests for llm property."""

    @patch("src.english_practice.agents.base.get_llm")
    def test_lazy_loading(self, mock_get_llm) -> None:
        mock_get_llm.return_value = MagicMock()
        agent = _TestAgent()
        assert agent._llm is None
        _ = agent.llm
        assert agent._llm is not None
        mock_get_llm.assert_called_once()

    @patch("src.english_practice.agents.base.get_llm")
    def test_caches_llm(self, mock_get_llm) -> None:
        mock_get_llm.return_value = MagicMock()
        agent = _TestAgent()
        llm1 = agent.llm
        llm2 = agent.llm
        assert llm1 is llm2
        mock_get_llm.assert_called_once()
