"""Tests for AnswersAgent."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.english_practice.agents.answers import AnswersAgent
from src.english_practice.models.agents import ExerciseAnswersOutput, QuestionAnswerItem


class TestAnswersAgent:
    """Tests for AnswersAgent."""

    def test_prompt_template_set(self) -> None:
        assert AnswersAgent.PROMPT_TEMPLATE == "answers.j2"

    def test_render_with_questions(self) -> None:
        agent = AnswersAgent()
        result = agent.render(
            MagicMock(questions=[{"question_id": "1"}], topic_name="Test")
        )
        assert isinstance(result, str)
        assert "1" in result

    @pytest.mark.asyncio
    async def test_extract_exercise_calls_invoke_structured(self, tmp_path) -> None:
        agent = AnswersAgent()
        img_path = tmp_path / "test.png"
        img_path.write_bytes(b"fake_png_data")

        expected = ExerciseAnswersOutput(
            questions=[QuestionAnswerItem(question_id="1", is_open_ended=False)]
        )

        with patch.object(agent, "invoke_structured", return_value=expected) as mock_invoke:
            result = await agent.extract_exercise(
                image_path=img_path,
                questions=[{"question_id": "1", "short_answer": "yes"}],
                topic_name="Test",
            )

            assert result == expected
            mock_invoke.assert_called_once()
            assert mock_invoke.call_args[1]["image_data"] == b"fake_png_data"
            assert mock_invoke.call_args[1]["output_model"] == ExerciseAnswersOutput

    @pytest.mark.asyncio
    async def test_extract_missing_image(self) -> None:
        agent = AnswersAgent()
        missing_path = Path("/nonexistent/test.png")

        expected = ExerciseAnswersOutput(questions=[])

        with patch.object(agent, "invoke_structured", return_value=expected) as mock_invoke:
            result = await agent.extract_exercise(
                image_path=missing_path,
                questions=[],
                topic_name="Test",
            )

            assert result == expected
            mock_invoke.assert_called_once()
            assert mock_invoke.call_args[1]["image_data"] is None
