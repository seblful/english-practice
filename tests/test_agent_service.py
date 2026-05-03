"""Tests for AgentService."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.english_practice.services.agent_service import AgentService


class TestAgentService:
    """Tests for AgentService."""

    @pytest.fixture(autouse=True)
    def mock_agents(self) -> None:
        """Mock the underlying agents to avoid LLM calls."""
        with patch("src.english_practice.services.agent_service.EvaluateAnswerAgent") as mock_eval, \
             patch("src.english_practice.services.agent_service.AssistantAgent") as mock_asst:
            self.mock_eval_instance = AsyncMock()
            self.mock_asst_instance = Mock()
            self.mock_asst_instance.assist = AsyncMock()
            self.mock_asst_instance.on_new_image = Mock()
            mock_eval.return_value = self.mock_eval_instance
            mock_asst.return_value = self.mock_asst_instance
            yield

    def test_on_new_image_calls_assistant_on_new_image(self) -> None:
        service = AgentService()
        service.on_new_image(1, 5)
        self.mock_asst_instance.on_new_image.assert_called_once()

    def test_on_new_image_passes_exercise_id(self) -> None:
        service = AgentService()
        service.on_new_image(1, 5)
        args, _ = self.mock_asst_instance.on_new_image.call_args
        assert args[1] == 5  # exercise_id

    def test_clear_all_history(self) -> None:
        service = AgentService()
        with patch.object(service, "_chat_history_manager") as mock_chm:
            service.clear_all_history(1)
            mock_chm.clear_user_history.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_evaluate_answer_passes_through(self) -> None:
        self.mock_eval_instance.evaluate = AsyncMock(
            return_value=Mock(is_correct=True, answer_idx=[0])
        )
        service = AgentService()
        result = await service.evaluate_answer(
            image_data=b"test",
            question_number="1",
            user_input="my answer",
            short_answers=["a"],
            full_answers=["b"],
            is_open_ended=False,
            topic_name="Test",
            rule="some rule",
        )
        assert result.is_correct is True
        self.mock_eval_instance.evaluate.assert_called_once_with(
            image_data=b"test",
            question_number="1",
            user_input="my answer",
            short_answers=["a"],
            full_answers=["b"],
            is_open_ended=False,
            topic_name="Test",
            rule="some rule",
        )

    @pytest.mark.asyncio
    async def test_evaluate_answer_no_rule(self) -> None:
        self.mock_eval_instance.evaluate = AsyncMock(
            return_value=Mock(is_correct=False, answer_idx=[])
        )
        service = AgentService()
        result = await service.evaluate_answer(
            image_data=b"test",
            question_number="2",
            user_input="wrong",
            short_answers=["a"],
            full_answers=["b"],
            is_open_ended=False,
            topic_name="Test",
            rule=None,
        )
        assert result.is_correct is False
        self.mock_eval_instance.evaluate.assert_called_once()

    @pytest.mark.asyncio
    async def test_assist_passes_through_with_exercise_id(self) -> None:
        self.mock_asst_instance.assist = AsyncMock(
            return_value=Mock(answer="helpful response")
        )
        service = AgentService()
        result = await service.assist(
            user_id=1,
            image_data=b"test",
            question_number="1",
            user_input="help me",
            topic_name="Test",
            exercise_id=5,
        )
        assert result.answer == "helpful response"
        self.mock_asst_instance.assist.assert_called_once()
        args, kwargs = self.mock_asst_instance.assist.call_args
        assert kwargs["user_id"] == 1
        assert kwargs["exercise_id"] == 5
        assert kwargs["image_data"] == b"test"

    @pytest.mark.asyncio
    async def test_assist_without_exercise_id(self) -> None:
        self.mock_asst_instance.assist = AsyncMock(
            return_value=Mock(answer="response")
        )
        service = AgentService()
        result = await service.assist(
            user_id=1,
            image_data=b"test",
            question_number="1",
            user_input="help",
            topic_name="Test",
        )
        assert result.answer == "response"
