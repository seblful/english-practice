"""Tests for rendering the text a grading request carries."""

import pytest
from pydantic import BaseModel

from practice_core.errors import ConfigurationError
from practice_core.grading import EvaluateAnswerInput
from practice_core.models import QuestionAnswer
from practice_core.prompts import render_decision_input


def _context(**overrides: object) -> EvaluateAnswerInput:
    """Return a grading context, with fields overridden as needed."""
    fields: dict[str, object] = {
        "question_number": "3",
        "user_input": "is doing",
        "answers": [
            QuestionAnswer(short_answer="is doing", full_answer="He **is doing** it.")
        ],
        "is_open_ended": False,
        "topic_name": "Present Tenses",
        "rule": "Use present continuous",
    }
    fields.update(overrides)
    return EvaluateAnswerInput.model_validate(fields)


class TestRenderDecisionInput:
    def test_carries_the_attempt(self) -> None:
        text = render_decision_input(_context())

        assert "Topic: Present Tenses" in text
        assert "Question: 3" in text
        assert 'Student\'s answer: "is doing"' in text
        assert "Use present continuous" in text

    def test_a_closed_question_lists_the_accepted_answers(self) -> None:
        text = render_decision_input(_context())

        assert "closed" in text
        assert '0. short: "is doing" | full: "He is doing it."' in text

    def test_the_book_bold_markers_are_dropped(self) -> None:
        assert "**" not in render_decision_input(_context())

    def test_an_open_question_lists_none(self) -> None:
        """Showing a database answer for a free-form question invites matching."""
        text = render_decision_input(_context(is_open_ended=True))

        assert "Accepted answers" not in text
        assert "open-ended" in text

    def test_a_closed_question_without_answers_reads_as_open(self) -> None:
        text = render_decision_input(_context(answers=[]))

        assert "Accepted answers" not in text
        assert "open-ended" in text

    def test_a_question_without_a_rule_omits_it(self) -> None:
        assert "Grammar rule" not in render_decision_input(_context(rule=None))

    def test_a_context_the_template_does_not_fit_is_an_error(self) -> None:
        """A renamed field used to yield a hollow request the provider billed for."""

        class Mismatched(BaseModel):
            question_number: str

        with pytest.raises(ConfigurationError, match=r"decision\.j2"):
            render_decision_input(Mismatched(question_number="3"))  # ty: ignore
