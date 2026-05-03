"""Tests for AssistantAgent."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.english_practice.agents.assistant import AssistantAgent
from src.english_practice.models.agents import AssistantContext, AssistantOutput, ChatMessage
from src.english_practice.services.chat_history import ChatHistoryManager


class TestAssistantAgent:
    """Tests for AssistantAgent."""

    def test_prompt_template_set(self) -> None:
        assert AssistantAgent.PROMPT_TEMPLATE == "assistant.j2"

    def test_render_with_history(self) -> None:
        agent = AssistantAgent()
        context = AssistantContext(
            question_number="1",
            user_input="help me",
            topic_name="Test",
            chat_history=[
                ChatMessage(role="user", content="previous q"),
                ChatMessage(role="assistant", content="previous a"),
            ],
        )
        result = agent.render(context)
        assert isinstance(result, str)
        assert "1" in result
        assert "help me" in result

    def test_render_without_history(self) -> None:
        agent = AssistantAgent()
        context = AssistantContext(
            question_number="2",
            user_input="help",
            topic_name="Test",
        )
        result = agent.render(context)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_assist_calls_invoke_and_adds_to_history(self) -> None:
        agent = AssistantAgent()
        expected_output = AssistantOutput(answer="Here is help")
        chat_history = ChatHistoryManager()

        with patch.object(agent, "invoke_structured", return_value=expected_output) as mock_invoke:
            result = await agent.assist(
                user_id=1,
                image_data=b"img",
                question_number="1",
                user_input="help me",
                topic_name="Test",
                chat_history_manager=chat_history,
                exercise_id=5,
            )

            assert result == expected_output
            mock_invoke.assert_called_once()
            assert mock_invoke.call_args[1]["image_data"] == b"img"
            assert mock_invoke.call_args[1]["output_model"] == AssistantOutput

            # Check history was updated
            history = chat_history.get_history(1, 5)
            assert len(history) == 2
            assert history[0]["role"] == "user"
            assert history[0]["content"] == "help me"
            assert history[1]["role"] == "assistant"
            assert history[1]["content"] == "Here is help"

    @pytest.mark.asyncio
    async def test_assist_without_exercise_id(self) -> None:
        agent = AssistantAgent()
        expected_output = AssistantOutput(answer="response")
        chat_history = ChatHistoryManager()

        with patch.object(agent, "invoke_structured", return_value=expected_output):
            result = await agent.assist(
                user_id=1,
                image_data=b"img",
                question_number="1",
                user_input="hello",
                topic_name="Test",
                chat_history_manager=chat_history,
            )

            assert result.answer == "response"
            # History should be keyed by None
            history = chat_history.get_history(1, None)
            assert len(history) == 2

    def test_on_new_image_calls_chat_history(self) -> None:
        agent = AssistantAgent()
        chat_history = MagicMock()
        agent.on_new_image(1, 5, chat_history)
        chat_history.on_new_image.assert_called_once_with(1, 5)
