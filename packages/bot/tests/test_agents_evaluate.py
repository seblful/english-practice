"""Tests for EvaluateAnswerAgent."""

from unittest.mock import MagicMock, patch

import pytest
from practice_core.grading import EvaluateAnswerInput, EvaluateAnswerOutput
from practice_core.models import Question, QuestionAnswer
from practice_core.prompts import render_evaluate_prompt

from practice_bot.agents.evaluate import EvaluateAnswerAgent


@pytest.fixture
def question() -> Question:
    """A closed question with a rule attached."""
    return Question(
        id=1,
        question_id="3",
        is_open_ended=False,
        section_letter="A",
        rule="Use present continuous",
    )


class TestEvaluateAnswerAgent:
    """Tests for EvaluateAnswerAgent."""

    @pytest.mark.asyncio
    async def test_evaluate_calls_invoke_structured(self, question: Question) -> None:
        agent = EvaluateAnswerAgent(MagicMock())
        expected = EvaluateAnswerOutput(is_correct=True, answer_idx=[0])

        with patch.object(
            agent, "invoke_structured", return_value=expected
        ) as mock_invoke:
            result = await agent.evaluate(
                question,
                user_input="test",
                answers=[QuestionAnswer(short_answer="a", full_answer="b")],
                topic_name="Test",
                image=b"img",
            )

        assert result == expected
        mock_invoke.assert_called_once()
        assert mock_invoke.call_args[1]["image"] == b"img"
        assert mock_invoke.call_args[1]["output_model"] == EvaluateAnswerOutput

    @pytest.mark.asyncio
    async def test_sends_the_shared_grading_prompt(self, question: Question) -> None:
        """The app grades with this same text, so it must not be rebuilt here."""
        agent = EvaluateAnswerAgent(MagicMock())
        answers = [QuestionAnswer(short_answer="is doing", full_answer="He is.")]

        with patch.object(
            agent,
            "invoke_structured",
            return_value=EvaluateAnswerOutput(is_correct=False),
        ) as mock_invoke:
            await agent.evaluate(
                question,
                user_input="is doing",
                answers=answers,
                topic_name="Present Tenses",
            )

        assert mock_invoke.call_args[1]["prompt"] == render_evaluate_prompt(
            EvaluateAnswerInput.for_question(
                question,
                user_input="is doing",
                answers=answers,
                topic_name="Present Tenses",
            )
        )

    @pytest.mark.asyncio
    async def test_the_question_carries_its_own_context(self) -> None:
        """Nothing about the question is restated by the caller any more."""
        agent = EvaluateAnswerAgent(MagicMock())
        open_ended = Question(id=2, question_id="7", is_open_ended=True)

        with patch.object(
            agent,
            "invoke_structured",
            return_value=EvaluateAnswerOutput(is_correct=True),
        ) as mock_invoke:
            await agent.evaluate(
                open_ended,
                user_input="my own sentence",
                answers=[],
                topic_name="Writing",
            )

        prompt = mock_invoke.call_args[1]["prompt"]
        assert prompt == render_evaluate_prompt(
            EvaluateAnswerInput.for_question(
                open_ended,
                user_input="my own sentence",
                answers=[],
                topic_name="Writing",
            )
        )
