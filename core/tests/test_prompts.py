"""Tests for rendering the shared grading prompt."""

import pytest
from pydantic import BaseModel

from practice_core.errors import ConfigurationError
from practice_core.grading import EvaluateAnswerInput
from practice_core.models import QuestionAnswer
from practice_core.prompts import _template, render_evaluate_prompt


def _context(**overrides: object) -> EvaluateAnswerInput:
    """Return a grading context, with fields overridden as needed."""
    fields: dict[str, object] = {
        "question_number": "3",
        "user_input": "is doing",
        "answers": [QuestionAnswer(short_answer="is doing", full_answer="He is.")],
        "is_open_ended": False,
        "topic_name": "Present Tenses",
        "rule": "Use present continuous",
    }
    fields.update(overrides)
    return EvaluateAnswerInput.model_validate(fields)


class TestRenderEvaluatePrompt:
    def test_carries_the_attempt_into_the_prompt(self) -> None:
        prompt = render_evaluate_prompt(_context())

        assert "Present Tenses" in prompt
        assert "<QuestionNumber>3</QuestionNumber>" in prompt
        assert "<StudentAnswer>is doing</StudentAnswer>" in prompt
        assert "Use present continuous" in prompt

    def test_a_closed_question_lists_the_expected_answers(self) -> None:
        prompt = render_evaluate_prompt(_context())

        # The grading rules mention the tag by name, so only the closing tag
        # tells the block apart from the prose that refers to it.
        assert "</ExpectedAnswers>" in prompt
        assert '0: short: "is doing"' in prompt
        assert "<QuestionType>CLOSED</QuestionType>" in prompt

    def test_an_open_question_lists_none(self) -> None:
        """Showing a database answer for a free-form question invites matching."""
        prompt = render_evaluate_prompt(_context(is_open_ended=True))

        assert "</ExpectedAnswers>" not in prompt
        assert "<QuestionType>OPEN</QuestionType>" in prompt
        assert "OPEN-ENDED" in prompt

    def test_a_question_without_a_rule_omits_the_block(self) -> None:
        prompt = render_evaluate_prompt(_context(rule=None))

        assert "</GrammarRule>" not in prompt

    def test_always_asks_for_raw_json(self) -> None:
        prompt = render_evaluate_prompt(_context())

        assert '"is_correct": boolean' in prompt
        assert "Return ONLY a valid, raw JSON object" in prompt

    def test_the_template_is_compiled_once(self) -> None:
        assert _template("evaluate.j2") is _template("evaluate.j2")

    def test_a_template_that_was_not_packaged(self) -> None:
        with pytest.raises(ConfigurationError, match="not packaged"):
            _template("absent.j2")

    def test_a_context_the_template_does_not_fit_is_an_error(self) -> None:
        """A renamed field used to yield a hollow prompt the provider billed for."""

        class Mismatched(BaseModel):
            question_number: str

        with pytest.raises(ConfigurationError, match=r"evaluate\.j2"):
            render_evaluate_prompt(Mismatched(question_number="3"))  # ty: ignore
