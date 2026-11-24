"""Tests for the shared grading contract."""

import pytest
from pydantic import ValidationError

from practice_core.grading import (
    EvaluateAnswerInput,
    EvaluateAnswerOutput,
    answers_to_show,
)
from practice_core.models import Exercise, Question, QuestionAnswer


class TestAnswersToShow:
    def test_shows_every_match(self, answers: list[QuestionAnswer]) -> None:
        assert answers_to_show(answers, [0, 1]) == tuple(answers)

    def test_shows_only_the_matches(self, answers: list[QuestionAnswer]) -> None:
        assert answers_to_show(answers, [1]) == (answers[1],)

    def test_no_match_falls_back_to_the_canonical_answer(
        self, answers: list[QuestionAnswer]
    ) -> None:
        assert answers_to_show(answers, []) == (answers[0],)

    def test_an_index_that_does_not_exist_is_ignored(
        self, answers: list[QuestionAnswer]
    ) -> None:
        """A hallucinated index must not raise, and must not hide the answer."""
        assert answers_to_show(answers, [7, -3]) == (answers[0],)

    def test_a_question_with_no_answers_shows_nothing(self) -> None:
        assert answers_to_show([], [0]) == ()


class TestTheGateOnDirectConstruction:
    """Whatever builds a verdict goes through the same validators."""

    def test_nonsense_indexes_are_dropped(self) -> None:
        built = EvaluateAnswerOutput(is_correct=True, answer_idx=[0, "1", -2, True, 3])  # type: ignore[list-item]

        assert built.answer_idx == [0, 3]

    def test_an_index_list_that_is_not_a_list(self) -> None:
        assert EvaluateAnswerOutput(is_correct=False, answer_idx=7).answer_idx == []  # type: ignore[arg-type]

    def test_a_verdict_that_is_not_a_boolean_is_refused(self) -> None:
        """Pydantic would read ``"yes"`` as ``True`` without the validator."""
        with pytest.raises(ValidationError, match="did not say"):
            EvaluateAnswerOutput(is_correct="yes")  # type: ignore[arg-type]

    def test_a_truthy_integer_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="did not say"):
            EvaluateAnswerOutput(is_correct=1)  # type: ignore[arg-type]


class TestEvaluateAnswerInputForQuestion:
    def test_reads_the_prompt_context_off_the_question(
        self, question: Question, answers: list[QuestionAnswer]
    ) -> None:
        context = EvaluateAnswerInput.for_question(
            question,
            user_input="is doing",
            answers=answers,
            topic_name="Present Tenses",
            unit_title="Present Continuous",
        )

        assert context == EvaluateAnswerInput(
            question_number=question.question_id,
            user_input="is doing",
            answers=answers,
            is_open_ended=question.is_open_ended,
            unit_title="Present Continuous",
            topic_name="Present Tenses",
            rule=question.rule,
        )

    def test_an_open_ended_question_carries_its_flag(self, exercise: Exercise) -> None:
        """The prompt branches on it, so it must not be dropped on the way."""
        open_ended = Question(id=9, question_id="3", is_open_ended=True)

        context = EvaluateAnswerInput.for_question(
            open_ended,
            user_input="anything",
            answers=[],
            topic_name="Any",
            unit_title=None,
        )

        assert context.is_open_ended is True
        assert context.rule is None
