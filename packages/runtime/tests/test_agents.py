"""Tests for BaseAgent.

The prompt these render is `practice_core`'s own grading template. It is a
dependency of this package and it is packaged the way every prompt is, so the
tests need no fixture template of their own — and they exercise the same
resource-reading path a real agent uses.
"""

import base64
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import HumanMessage
from practice_core.grading import EvaluateAnswerInput
from practice_core.models import QuestionAnswer
from pydantic import BaseModel

from practice_runtime.agents import BaseAgent
from practice_runtime.errors import AgentError, ConfigurationError


def _parts(msg: HumanMessage) -> list[dict]:
    """Return the message's content blocks, asserting the multimodal shape."""
    assert isinstance(msg.content, list)
    assert all(isinstance(part, dict) for part in msg.content)
    return [part for part in msg.content if isinstance(part, dict)]


def _context() -> EvaluateAnswerInput:
    """A context the shared grading template fits."""
    return EvaluateAnswerInput(
        question_number="3",
        user_input="is doing",
        answers=[QuestionAnswer(short_answer="is doing", full_answer="He is.")],
        is_open_ended=False,
        topic_name="Present Tenses",
    )


class DummyModel(BaseModel):
    name: str


class _TestAgent(BaseAgent):
    """Concrete agent for testing (not collected by pytest)."""

    PROMPT_ANCHOR = "practice_core"
    PROMPT_TEMPLATE = "evaluate.j2"


def _structured_llm(result: object) -> MagicMock:
    """Return a chat model whose structured call yields ``result``."""
    llm = MagicMock()
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=result)
    llm.with_structured_output = MagicMock(return_value=structured)
    return llm


class TestRender:
    def test_renders_the_packaged_template(self) -> None:
        result = _TestAgent(MagicMock()).render(_context())

        assert "Present Tenses" in result
        assert "<StudentAnswer>is doing</StudentAnswer>" in result

    def test_a_context_the_template_does_not_fit_is_an_error(self) -> None:
        """Rendering the wrong model used to yield a hollow prompt, not a failure."""
        with pytest.raises(ConfigurationError, match=r"evaluate\.j2"):
            _TestAgent(MagicMock()).render(DummyModel(name="test"))

    def test_an_agent_without_a_template(self) -> None:
        with pytest.raises(ConfigurationError, match="PROMPT_TEMPLATE"):
            BaseAgent(MagicMock()).render(DummyModel(name="test"))

    def test_an_agent_without_an_anchor(self) -> None:
        """Naming a template but not its package would read the wrong package."""

        class _Anchorless(BaseAgent):
            PROMPT_TEMPLATE = "evaluate.j2"

        with pytest.raises(ConfigurationError, match="PROMPT_TEMPLATE"):
            _Anchorless(MagicMock()).render(_context())


class TestBuildMessage:
    def test_without_image(self) -> None:
        parts = _parts(_TestAgent(MagicMock())._build_message("hello"))

        assert len(parts) == 1
        assert parts[0]["text"] == "hello"

    def test_with_image(self) -> None:
        agent = _TestAgent(MagicMock())

        parts = _parts(agent._build_message("hello", image_data=b"hi"))

        assert len(parts) == 2
        encoded = base64.b64encode(b"hi").decode("utf-8")
        assert parts[1]["image_url"]["url"] == f"data:image/png;base64,{encoded}"


class TestInvokeStructured:
    async def test_returns_the_parsed_model(self) -> None:
        agent = _TestAgent(_structured_llm(DummyModel(name="response")))

        result = await agent.invoke_structured("test", DummyModel, image_data=b"img")

        assert result.name == "response"

    async def test_asks_the_provider_for_the_output_model(self) -> None:
        llm = _structured_llm(DummyModel(name="response"))

        await _TestAgent(llm).invoke_structured("test", DummyModel)

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


class TestClient:
    def test_the_injected_client_is_the_one_used(self) -> None:
        """Every agent in a process shares one client, and one pool with it."""
        llm = MagicMock()

        assert _TestAgent(llm).llm is llm
