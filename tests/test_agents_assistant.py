"""Tests for AssistantAgent."""

from unittest.mock import patch

from english_practice.agents.assistant import AssistantAgent
from english_practice.models.agents import (
    AssistantContext,
    AssistantOutput,
    ChatMessage,
)


class TestPrompt:
    """Tests for the rendered prompt."""

    def test_template_is_declared(self) -> None:
        assert AssistantAgent.PROMPT_TEMPLATE == "assistant.j2"

    def test_includes_the_question_and_input(self) -> None:
        context = AssistantContext(
            question_number="1", user_input="help me", topic_name="Test"
        )

        result = AssistantAgent().render(context)

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

        result = AssistantAgent().render(context)

        assert "<ChatHistory>" in result
        assert "previous q" in result
        assert "previous a" in result

    def test_omits_the_transcript_section_when_empty(self) -> None:
        context = AssistantContext(
            question_number="2", user_input="help", topic_name="Test"
        )

        assert "<ChatHistory>" not in AssistantAgent().render(context)


class TestAssist:
    """Tests for the LLM call."""

    async def test_passes_the_image_and_output_model(self) -> None:
        agent = AssistantAgent()
        expected = AssistantOutput(answer="Here is help")

        with patch.object(
            agent, "invoke_structured", return_value=expected
        ) as mock_invoke:
            result = await agent.assist(
                image_data=b"img",
                question_number="1",
                user_input="help me",
                topic_name="Test",
            )

        assert result == expected
        kwargs = mock_invoke.call_args.kwargs
        assert kwargs["image_data"] == b"img"
        assert kwargs["output_model"] is AssistantOutput

    async def test_renders_the_history_it_is_given(self) -> None:
        agent = AssistantAgent()

        with patch.object(
            agent, "invoke_structured", return_value=AssistantOutput(answer="a")
        ) as mock_invoke:
            await agent.assist(
                image_data=None,
                question_number="1",
                user_input="and now?",
                topic_name="Test",
                chat_history=[ChatMessage(role="user", content="previous q")],
            )

        assert "previous q" in mock_invoke.call_args.kwargs["prompt"]
