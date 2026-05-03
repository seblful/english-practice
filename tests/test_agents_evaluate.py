"""Tests for EvaluateAnswerAgent."""

from unittest.mock import patch

import pytest

from src.english_practice.agents.evaluate import EvaluateAnswerAgent
from src.english_practice.models.agents import EvaluateAnswerInput, EvaluateAnswerOutput


class TestEvaluateAnswerAgent:
    """Tests for EvaluateAnswerAgent."""

    def test_prompt_template_set(self) -> None:
        assert EvaluateAnswerAgent.PROMPT_TEMPLATE == "evaluate.j2"

    def test_render_returns_string(self) -> None:
        agent = EvaluateAnswerAgent()
        context = EvaluateAnswerInput(
            question_number="1",
            user_input="my answer",
            short_answers=["a"],
            full_answers=["b"],
            is_open_ended=False,
            topic_name="Test",
            rule="some rule",
        )
        result = agent.render(context)
        assert isinstance(result, str)
        assert len(result) > 0
        assert "1" in result
        assert "my answer" in result

    def test_render_without_rule(self) -> None:
        agent = EvaluateAnswerAgent()
        context = EvaluateAnswerInput(
            question_number="2",
            user_input="answer",
            short_answers=["a"],
            full_answers=["b"],
            is_open_ended=False,
            topic_name="Test",
        )
        result = agent.render(context)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_evaluate_calls_invoke_structured(self) -> None:
        agent = EvaluateAnswerAgent()
        expected = EvaluateAnswerOutput(is_correct=True, answer_idx=[0])

        with patch.object(agent, "invoke_structured", return_value=expected) as mock_invoke:
            result = await agent.evaluate(
                image_data=b"img",
                question_number="1",
                user_input="test",
                short_answers=["a"],
                full_answers=["b"],
                is_open_ended=False,
                topic_name="Test",
                rule="rule",
            )

            assert result == expected
            mock_invoke.assert_called_once()
            assert mock_invoke.call_args[1]["image_data"] == b"img"
            assert mock_invoke.call_args[1]["output_model"] == EvaluateAnswerOutput
