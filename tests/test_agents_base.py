"""Tests for BaseAgent."""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from english_practice.agents.base import BaseAgent, _prompt_env
from english_practice.errors import AgentError, ConfigurationError
from english_practice.models.agents import EvaluateAnswerInput
from english_practice.models.book import QuestionAnswer
from english_practice.settings import get_settings


def _parts(msg: HumanMessage) -> list[dict]:
    """Return the message's content blocks, asserting the multimodal shape."""
    assert isinstance(msg.content, list)
    assert all(isinstance(part, dict) for part in msg.content)
    return [part for part in msg.content if isinstance(part, dict)]


class DummyModel(BaseModel):
    name: str


class _TestAgent(BaseAgent):
    """Concrete agent for testing (not collected by pytest)."""

    PROMPT_TEMPLATE = "evaluate.j2"


def _structured_llm(result: object) -> MagicMock:
    """Return a chat model whose structured call yields ``result``."""
    llm = MagicMock()
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=result)
    llm.with_structured_output = MagicMock(return_value=structured)
    return llm


class TestPromptEnv:
    """Tests for the Jinja environment cache."""

    def test_cached_per_directory(self) -> None:
        prompts_dir = get_settings().paths.prompts_dir

        assert _prompt_env(prompts_dir) is _prompt_env(prompts_dir)


class TestRender:
    """Tests for prompt rendering."""

    def test_renders_the_template(self) -> None:
        result = _TestAgent().render(
            EvaluateAnswerInput(
                question_number="1",
                user_input="is doing",
                answers=[QuestionAnswer(short_answer="is doing", full_answer="He is.")],
                is_open_ended=False,
                topic_name="Present Tenses",
            )
        )

        assert "is doing" in result
        assert "Present Tenses" in result

    def test_a_context_the_template_does_not_fit_is_an_error(self) -> None:
        """Rendering the wrong model used to yield a hollow prompt, not a failure."""
        with pytest.raises(ConfigurationError, match=r"evaluate\.j2"):
            _TestAgent().render(DummyModel(name="test"))

    def test_agent_without_a_template_is_a_configuration_error(self) -> None:
        with pytest.raises(ConfigurationError, match="PROMPT_TEMPLATE"):
            BaseAgent().render(DummyModel(name="test"))


class TestBuildMessage:
    """Tests for assembling the multimodal message."""

    def test_without_image(self) -> None:
        parts = _parts(_TestAgent()._build_message("hello"))

        assert len(parts) == 1
        assert parts[0]["text"] == "hello"

    def test_with_image(self) -> None:
        parts = _parts(_TestAgent()._build_message("hello", image_data=b"hi"))

        assert len(parts) == 2
        encoded = base64.b64encode(b"hi").decode("utf-8")
        assert parts[1]["image_url"]["url"] == f"data:image/png;base64,{encoded}"


class TestInvokeStructured:
    """Tests for the structured LLM call."""

    async def test_returns_the_parsed_model(self) -> None:
        agent = _TestAgent(_structured_llm(DummyModel(name="response")))

        result = await agent.invoke_structured("test", DummyModel, image_data=b"img")

        assert result.name == "response"

    async def test_asks_the_provider_for_the_output_model(self) -> None:
        llm = _structured_llm(DummyModel(name="response"))
        agent = _TestAgent(llm)

        await agent.invoke_structured("test", DummyModel)

        llm.with_structured_output.assert_called_once_with(DummyModel)

    async def test_provider_failure_becomes_an_agent_error(self) -> None:
        """Handlers catch AgentError; a raw provider exception would escape."""
        llm = MagicMock()
        structured = MagicMock()
        structured.ainvoke = AsyncMock(side_effect=RuntimeError("429 rate limited"))
        llm.with_structured_output = MagicMock(return_value=structured)

        with pytest.raises(AgentError, match="DummyModel") as exc_info:
            await _TestAgent(llm).invoke_structured("test", DummyModel)

        assert isinstance(exc_info.value.__cause__, RuntimeError)


class TestLLMProperty:
    """Tests for how the chat model is obtained."""

    def test_injected_client_is_used(self) -> None:
        llm = MagicMock()

        assert _TestAgent(llm).llm is llm

    @patch("english_practice.agents.base.get_llm")
    def test_built_lazily_and_once(self, mock_get_llm: MagicMock) -> None:
        mock_get_llm.return_value = MagicMock()
        agent = _TestAgent()
        assert agent._llm is None

        assert agent.llm is agent.llm
        mock_get_llm.assert_called_once()
