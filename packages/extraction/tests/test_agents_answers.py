"""Tests for AnswersAgent."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from practice_extraction.agents.answers import AnswersAgent
from practice_extraction.models import (
    AnswersContext,
    AnswersQuestion,
    ExerciseAnswersOutput,
    QuestionAnswerItem,
)


class TestAnswersAgent:
    """Tests for AnswersAgent."""

    def test_the_prompt_travels_with_the_agent(self) -> None:
        assert AnswersAgent.PROMPT_TEMPLATE == "answers.j2"
        assert AnswersAgent.PROMPT_ANCHOR == "practice_extraction.agents"

    def test_render_with_questions(self) -> None:
        agent = AnswersAgent(MagicMock())
        context = AnswersContext(
            questions=[AnswersQuestion(question_id="7", short_answer="has been")],
            topic_name="Present Perfect",
        )

        result = agent.render(context)

        assert "id: 7, expected_short_answer: has been" in result
        assert "Present Perfect" in result

    @pytest.mark.asyncio
    async def test_extract_exercise_calls_invoke_structured(self, tmp_path) -> None:
        agent = AnswersAgent(MagicMock())
        img_path = tmp_path / "test.png"
        img_path.write_bytes(b"fake_png_data")

        expected = ExerciseAnswersOutput(
            questions=[QuestionAnswerItem(question_id="1", is_open_ended=False)]
        )

        with patch.object(
            agent, "invoke_structured", return_value=expected
        ) as mock_invoke:
            result = await agent.extract_exercise(
                image_path=img_path,
                questions=[AnswersQuestion(question_id="1", short_answer="yes")],
                topic_name="Test",
            )

            assert result == expected
            mock_invoke.assert_called_once()
            # The stage hands over the path. Reading it, and deciding what to do
            # when it is not there, is the base agent's job now.
            assert mock_invoke.call_args[1]["image"] == img_path
            assert mock_invoke.call_args[1]["output_model"] == ExerciseAnswersOutput

    @pytest.mark.asyncio
    async def test_extract_missing_image(self) -> None:
        agent = AnswersAgent(MagicMock())
        missing_path = Path("/nonexistent/test.png")

        expected = ExerciseAnswersOutput(questions=[])

        with patch.object(
            agent, "invoke_structured", return_value=expected
        ) as mock_invoke:
            result = await agent.extract_exercise(
                image_path=missing_path,
                questions=[],
                topic_name="Test",
            )

            assert result == expected
            mock_invoke.assert_called_once()
            assert mock_invoke.call_args[1]["image"] == missing_path
