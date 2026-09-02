"""Tests for EvaluateAnswerAgent.

The prompt itself is `practice_core`'s, and is tested there. What matters here
is that the agent sends *that* prompt, with the image and the output model the
provider needs.
"""

from unittest.mock import MagicMock, patch

import pytest
from practice_core.grading import EvaluateAnswerInput, EvaluateAnswerOutput
from practice_core.models import QuestionAnswer
from practice_core.prompts import render_evaluate_prompt

from practice_bot.agents.evaluate import EvaluateAnswerAgent


class TestEvaluateAnswerAgent:
    """Tests for EvaluateAnswerAgent."""

    @pytest.mark.asyncio
    async def test_evaluate_calls_invoke_structured(self) -> None:
        agent = EvaluateAnswerAgent(MagicMock())
        expected = EvaluateAnswerOutput(is_correct=True, answer_idx=[0])

        with patch.object(
            agent, "invoke_structured", return_value=expected
        ) as mock_invoke:
            result = await agent.evaluate(
                image_data=b"img",
                question_number="1",
                user_input="test",
                answers=[QuestionAnswer(short_answer="a", full_answer="b")],
                is_open_ended=False,
                topic_name="Test",
                rule="rule",
            )

        assert result == expected
        mock_invoke.assert_called_once()
        assert mock_invoke.call_args[1]["image_data"] == b"img"
        assert mock_invoke.call_args[1]["output_model"] == EvaluateAnswerOutput

    @pytest.mark.asyncio
    async def test_sends_the_shared_grading_prompt(self) -> None:
        """The app grades with this same text, so it must not be rebuilt here."""
        agent = EvaluateAnswerAgent(MagicMock())
        answers = [QuestionAnswer(short_answer="is doing", full_answer="He is.")]

        with patch.object(
            agent,
            "invoke_structured",
            return_value=EvaluateAnswerOutput(is_correct=False),
        ) as mock_invoke:
            await agent.evaluate(
                image_data=None,
                question_number="3",
                user_input="is doing",
                answers=answers,
                is_open_ended=False,
                topic_name="Present Tenses",
                rule="Use present continuous",
            )

        assert mock_invoke.call_args[1]["prompt"] == render_evaluate_prompt(
            EvaluateAnswerInput(
                question_number="3",
                user_input="is doing",
                answers=answers,
                is_open_ended=False,
                topic_name="Present Tenses",
                rule="Use present continuous",
            )
        )
