"""Tests for the reveal decision both front ends now share."""

from practice_core.grading import EvaluateAnswerOutput
from practice_core.models import Question, QuestionAnswer
from practice_core.reveal import reveal_for


def _graded(*, correct: bool, matched: list[int] | None = None) -> EvaluateAnswerOutput:
    """A verdict, with the indexes the grader reported."""
    return EvaluateAnswerOutput(is_correct=correct, answer_idx=matched or [])


class TestWhichAnswersAreShown:
    def test_a_graded_answer_shows_what_it_matched(
        self, question: Question, answers: list[QuestionAnswer]
    ) -> None:
        result = reveal_for(
            question,
            answers=answers,
            unit_number=1,
            evaluation=_graded(correct=True, matched=[1]),
        )

        assert result.answers == (answers[1],)

    def test_an_ungraded_answer_falls_back_to_the_canonical_one(
        self, question: Question, answers: list[QuestionAnswer]
    ) -> None:
        result = reveal_for(question, answers=answers, unit_number=1, evaluation=None)

        assert result.answers == (answers[0],)
        assert result.was_graded is False

    def test_an_open_ended_question_reveals_nothing(
        self, answers: list[QuestionAnswer]
    ) -> None:
        """The prompt forbids it: a stored phrasing is one to match, not an answer."""
        open_ended = Question(id=2, question_id="1", is_open_ended=True)

        result = reveal_for(
            open_ended,
            answers=answers,
            unit_number=1,
            evaluation=_graded(correct=False, matched=[0]),
        )

        assert result.answers == ()
        assert result.has_answer is False

    def test_a_question_the_book_has_no_answers_for(self, question: Question) -> None:
        result = reveal_for(question, answers=[], unit_number=1, evaluation=None)

        assert result.answers == ()
        assert result.show_full_answer is False


class TestWhetherTheFullSentenceIsShown:
    def test_a_wrong_answer_gets_the_whole_sentence(
        self, question: Question, answers: list[QuestionAnswer]
    ) -> None:
        result = reveal_for(
            question,
            answers=answers,
            unit_number=1,
            evaluation=_graded(correct=False, matched=[0]),
        )

        assert result.show_full_answer is True

    def test_a_correct_answer_gets_the_short_form_only(
        self, question: Question, answers: list[QuestionAnswer]
    ) -> None:
        """Confirmation should be quick to dismiss."""
        result = reveal_for(
            question,
            answers=answers,
            unit_number=1,
            evaluation=_graded(correct=True, matched=[0]),
        )

        assert result.show_full_answer is False

    def test_a_sentence_that_only_repeats_the_answer_is_skipped(
        self, question: Question
    ) -> None:
        """A question asking for a whole sentence prints it in both fields."""
        same = [
            QuestionAnswer(
                short_answer="He is doing his homework.",
                full_answer="**He is doing his homework.**",
            )
        ]

        result = reveal_for(
            question,
            answers=same,
            unit_number=1,
            evaluation=_graded(correct=False, matched=[0]),
        )

        assert result.show_full_answer is False

    def test_an_ungraded_reveal_shows_the_whole_sentence(
        self, question: Question, answers: list[QuestionAnswer]
    ) -> None:
        result = reveal_for(question, answers=answers, unit_number=1, evaluation=None)

        assert result.show_full_answer is True


class TestTheRule:
    def test_the_rule_is_offered_when_the_question_has_one(
        self, question: Question
    ) -> None:
        result = reveal_for(question, answers=[], unit_number=1, evaluation=None)

        assert result.rule == question.rule

    def test_no_rule_when_the_student_turned_them_off(self, question: Question) -> None:
        result = reveal_for(
            question, answers=[], unit_number=1, evaluation=None, show_rule=False
        )

        assert result.rule is None

    def test_no_rule_when_the_book_holds_only_blank_space(self) -> None:
        blank = Question(id=3, question_id="1", rule="   ")

        result = reveal_for(blank, answers=[], unit_number=1, evaluation=None)

        assert result.rule is None


class TestUnitReference:
    def test_names_the_unit_and_section(self, question: Question) -> None:
        result = reveal_for(question, answers=[], unit_number=12, evaluation=None)

        assert result.unit_reference == "12A"

    def test_a_question_with_no_section(self) -> None:
        no_section = Question(id=4, question_id="1")

        result = reveal_for(no_section, answers=[], unit_number=7, evaluation=None)

        assert result.unit_reference == "7"
