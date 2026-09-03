"""Tests for AssistantAgent."""

from unittest.mock import MagicMock, patch

import pytest

from practice_bot.agents.assistant import AssistantAgent
from practice_bot.models.agents import (
    AssistantContext,
    AssistantOutput,
    ChatMessage,
)


@pytest.fixture
def agent() -> AssistantAgent:
    """An agent over a stand-in client, so nothing reaches a provider."""
    return AssistantAgent(MagicMock())


class TestPrompt:
    """Tests for the rendered prompt."""

    def test_the_prompt_travels_with_the_agent(self) -> None:
        assert AssistantAgent.PROMPT_TEMPLATE == "assistant.j2"
        assert AssistantAgent.PROMPT_ANCHOR == "practice_bot.agents"

    def test_includes_the_question_and_input(self) -> None:
        context = AssistantContext(
            question_number="1", user_input="help me", topic_name="Test"
        )

        result = AssistantAgent(MagicMock()).render(context)

        assert "help me" in result
        assert "<QuestionNumber>1</QuestionNumber>" in result

    def test_includes_the_transcript_when_there_is_one(self) -> None:
        context = AssistantContext(
            question_number="1",
            user_input="and now?",
            topic_name="Test",
            chat_history=[
                ChatMessage(role="user", content="previous q"),
                ChatMessage(role="assistant", content="previous a"),
            ],
        )

        result = AssistantAgent(MagicMock()).render(context)

        assert "<ChatHistory>" in result
        assert "previous q" in result
        assert "previous a" in result

    def test_omits_the_transcript_section_when_empty(self) -> None:
        context = AssistantContext(
            question_number="2", user_input="help", topic_name="Test"
        )

        assert "<ChatHistory>" not in AssistantAgent(MagicMock()).render(context)


class TestAssist:
    """Tests for the LLM call."""

    async def test_passes_the_image_and_output_model(
        self, agent: AssistantAgent
    ) -> None:
        expected = AssistantOutput(answer="Here is help")

        with patch.object(
            agent, "invoke_structured", return_value=expected
        ) as mock_invoke:
            result = await agent.assist(
                image=b"img",
                question_number="1",
                user_input="help me",
                topic_name="Test",
            )

        assert result == expected
        kwargs = mock_invoke.call_args.kwargs
        assert kwargs["image"] == b"img"
        assert kwargs["output_model"] is AssistantOutput

    async def test_renders_the_history_it_is_given(self, agent: AssistantAgent) -> None:

        with patch.object(
            agent, "invoke_structured", return_value=AssistantOutput(answer="a")
        ) as mock_invoke:
            await agent.assist(
                image=None,
                question_number="1",
                user_input="and now?",
                topic_name="Test",
                chat_history=[ChatMessage(role="user", content="previous q")],
            )

        assert "previous q" in mock_invoke.call_args.kwargs["prompt"]
