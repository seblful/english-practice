"""Tests for RulesAgent."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.english_practice.agents.rules import RulesAgent
from src.english_practice.models.agents import ExerciseRulesOutput, QuestionRuleItem


class TestRulesAgent:
    """Tests for RulesAgent."""

    def test_prompt_template_set(self) -> None:
        assert RulesAgent.PROMPT_TEMPLATE == "rules.j2"

    def test_render_with_questions(self) -> None:
        from src.english_practice.models.agents import RulesContext
        agent = RulesAgent()
        context = RulesContext(
            questions=[{"question_id": "1"}],
            rules_md="# Grammar",
            topic_name="Test",
        )
        result = agent.render(context)
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_extract_exercise_calls_invoke_structured(self, tmp_path) -> None:
        agent = RulesAgent()
        img_path = tmp_path / "test.png"
        img_path.write_bytes(b"fake_png_data")

        expected = ExerciseRulesOutput(
            questions=[QuestionRuleItem(question_id="1", section_letter="A", rule="rule")]
        )

        with patch.object(agent, "invoke_structured", return_value=expected) as mock_invoke:
            result = await agent.extract_exercise(
                image_path=img_path,
                questions=[{"question_id": "1"}],
                rules_md="# Grammar rule",
                topic_name="Test",
            )

            assert result == expected
            mock_invoke.assert_called_once()
            assert mock_invoke.call_args[1]["image_data"] == b"fake_png_data"
            assert mock_invoke.call_args[1]["output_model"] == ExerciseRulesOutput

    @pytest.mark.asyncio
    async def test_extract_missing_image_passes_none(self) -> None:
        agent = RulesAgent()
        missing_path = Path("/nonexistent/test.png")

        expected = ExerciseRulesOutput(questions=[])

        with patch.object(agent, "invoke_structured", return_value=expected) as mock_invoke:
            result = await agent.extract_exercise(
                image_path=missing_path,
                questions=[],
                rules_md="",
                topic_name="Test",
            )

            assert result == expected
            assert mock_invoke.call_args[1]["image_data"] is None
