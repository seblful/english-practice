"""Tests for the lesson both front ends can now run.

These assert through the transitions rather than by setting fields, which is
the point of moving them here: recording an outcome used to be the caller's
duty, so the rule that a revealed answer never counts as correct was enforced
by whoever remembered to pass ``correct=False``.
"""

from dataclasses import replace

import pytest

from practice_core.errors import PracticeError
from practice_core.grading import EvaluateAnswerOutput
from practice_core.lesson import (
    LESSON_LENGTH,
    RANDOM_TOPIC_LABEL,
    ActiveExercise,
    Lesson,
    topic_label,
)
from practice_core.models import Exercise, Question, QuestionAnswer, Unit


@pytest.fixture
def active(exercise: Exercise, answers: list[QuestionAnswer]) -> ActiveExercise:
    """A question in front of the user, with its answers already read."""
    return ActiveExercise(
        exercise=exercise,
        question=exercise.questions[0],
        topic_id=1,
        topic_name="Present Tenses",
        image=b"\x89PNG",
        answers=tuple(answers),
    )


@pytest.fixture
def lesson(active: ActiveExercise) -> Lesson:
    """A lesson with its first question on screen."""
    return Lesson(topic_id=1, topic_name="Present Tenses", active=active)


def _answer(lesson: Lesson, active: ActiveExercise, *, correct: bool) -> None:
    """Draw a question and grade it, the way a front end drives a run.

    A fresh copy each time, because a run draws a fresh question each time and
    a question may only be settled once.
    """
    lesson.advance(replace(active))
    lesson.check(EvaluateAnswerOutput(is_correct=correct))


class TestTopicLabel:
    def test_the_requested_topic_wins(self, unit: Unit) -> None:
        assert topic_label(topic_name="Past Tenses", unit=unit) == "Past Tenses"

    def test_a_mixed_run_takes_the_topic_the_book_files_the_unit_under(
        self, unit: Unit
    ) -> None:
        assert topic_label(topic_name=None, unit=unit) == unit.topic_name

    def test_a_unit_the_book_files_nowhere(self) -> None:
        loose = Unit(id=9, unit_number=9, title="Reported Speech")

        assert topic_label(topic_name=None, unit=loose) == RANDOM_TOPIC_LABEL


class TestActiveExercise:
    def test_a_fresh_question_is_not_revealed(self, active: ActiveExercise) -> None:
        assert active.is_revealed is False

    def test_reveals_through_the_shared_decision(
        self, active: ActiveExercise, answers: list[QuestionAnswer]
    ) -> None:
        active.evaluation = EvaluateAnswerOutput(is_correct=False, answer_idx=[1])

        result = active.reveal()

        assert result.answers == (answers[1],)
        assert result.rule == active.question.rule

    def test_passes_the_rule_setting_through(self, active: ActiveExercise) -> None:
        assert active.reveal(show_rule=False).rule is None


class TestCheck:
    def test_a_correct_answer_is_recorded(self, lesson: Lesson) -> None:
        lesson.check(EvaluateAnswerOutput(is_correct=True))

        assert lesson.outcomes == [True]
        assert lesson.correct == 1

    def test_the_verdict_lands_on_the_question(self, lesson: Lesson) -> None:
        verdict = EvaluateAnswerOutput(is_correct=False, answer_idx=[0])

        returned = lesson.check(verdict)

        assert returned.evaluation is verdict
        assert returned.is_revealed is True

    def test_a_settled_question_refuses_a_second_outcome(self, lesson: Lesson) -> None:
        """One question, one of the run's slots.

        Nothing enforced this: a failed grading followed by a verdict spent
        two of the ten, so the bar and the counter reported a lesson longer
        than the one the student sat. The app was safe only because the screen
        hides the Check button once an answer is revealed.
        """
        lesson.grading_failed()

        with pytest.raises(PracticeError, match="already has an outcome"):
            lesson.check(EvaluateAnswerOutput(is_correct=True))

        assert lesson.outcomes == [False]

    def test_a_verdict_clears_an_earlier_failure_on_the_same_question(
        self, active: ActiveExercise
    ) -> None:
        """The transition owns both fields, so neither can be left standing."""
        active.give_up()
        active.record(EvaluateAnswerOutput(is_correct=True))

        assert active.ungraded is False
        assert active.answered is True

    def test_checking_with_nothing_on_screen(self) -> None:
        empty = Lesson(topic_id=None, topic_name="Mixed")

        with pytest.raises(PracticeError, match="no question is on screen"):
            empty.check(EvaluateAnswerOutput(is_correct=True))


class TestBeingGraded:
    """The claim that stops one answer being graded twice."""

    def test_the_claim_is_held_for_the_length_of_the_call(
        self, active: ActiveExercise
    ) -> None:
        assert active.grading is False

        with active.being_graded():
            assert active.grading is True

        assert active.grading is False

    def test_the_claim_is_released_when_the_grading_fails(
        self, active: ActiveExercise
    ) -> None:
        """A failed grading leaves the question open for another attempt."""
        with pytest.raises(RuntimeError), active.being_graded():
            raise RuntimeError("provider down")

        assert active.grading is False


class TestRevealAndFailure:
    def test_revealing_spends_the_question_but_earns_nothing(
        self, lesson: Lesson
    ) -> None:
        lesson.reveal_answer()

        assert lesson.outcomes == [False]
        assert lesson.answered == 1
        assert lesson.correct == 0

    def test_a_run_of_reveals_is_not_a_perfect_lesson(
        self, lesson: Lesson, active: ActiveExercise
    ) -> None:
        for _ in range(3):
            lesson.advance(replace(active))
            lesson.reveal_answer()

        assert lesson.accuracy == 0.0

    def test_a_failed_grading_spends_the_question(self, lesson: Lesson) -> None:
        """A run has a fixed length, so there is nowhere to put a retry."""
        returned = lesson.grading_failed()

        assert lesson.outcomes == [False]
        assert returned.ungraded is True
        assert returned.reveal().was_graded is False

    def test_revealing_with_nothing_on_screen(self) -> None:
        empty = Lesson(topic_id=None, topic_name="Mixed")

        with pytest.raises(PracticeError, match="no question is on screen"):
            empty.reveal_answer()

    def test_failing_with_nothing_on_screen(self) -> None:
        empty = Lesson(topic_id=None, topic_name="Mixed")

        with pytest.raises(PracticeError, match="no question is on screen"):
            empty.grading_failed()


class TestProgress:
    def test_a_new_lesson_is_on_its_first_question(self, lesson: Lesson) -> None:
        assert lesson.position == 1
        assert lesson.progress == 0.0
        assert lesson.is_complete is False

    def test_the_counter_holds_while_the_verdict_is_read(self, lesson: Lesson) -> None:
        """Otherwise "2/10" appears over the verdict for question one."""
        lesson.check(EvaluateAnswerOutput(is_correct=True))

        assert lesson.position == 1

    def test_the_counter_moves_once_the_next_question_is_drawn(
        self, lesson: Lesson, active: ActiveExercise
    ) -> None:
        lesson.check(EvaluateAnswerOutput(is_correct=True))
        lesson.advance(
            ActiveExercise(
                exercise=active.exercise,
                question=active.question,
                topic_id=1,
                topic_name="Present Tenses",
            )
        )

        assert lesson.position == 2

    def test_a_finished_run(self, lesson: Lesson, active: ActiveExercise) -> None:
        for _ in range(LESSON_LENGTH):
            _answer(lesson, active, correct=True)

        assert lesson.is_complete is True
        assert lesson.progress == 1.0
        assert lesson.accuracy == 1.0

    def test_the_counter_stops_at_the_length(
        self, lesson: Lesson, active: ActiveExercise
    ) -> None:
        for _ in range(LESSON_LENGTH + 3):
            _answer(lesson, active, correct=True)
        lesson.advance(
            ActiveExercise(
                exercise=active.exercise,
                question=Question(id=5, question_id="5"),
                topic_id=1,
                topic_name="Present Tenses",
            )
        )

        assert lesson.position == LESSON_LENGTH

    def test_an_untouched_lesson_has_no_accuracy_to_report(self) -> None:
        empty = Lesson(topic_id=None, topic_name="Mixed")

        assert empty.accuracy == 0.0


class TestFinish:
    def test_takes_the_question_off_screen(self, lesson: Lesson) -> None:
        lesson.check(EvaluateAnswerOutput(is_correct=True))

        lesson.finish()

        assert lesson.active is None
