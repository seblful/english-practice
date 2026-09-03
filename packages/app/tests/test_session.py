"""Tests for the lesson: the run of questions a practice screen walks through.

The screen reads its progress bar, its counter and its result off this one
object, so what is checked here is that those three can never disagree.
"""

import pytest
from practice_core.grading import EvaluateAnswerOutput
from practice_core.models import Exercise, Question, QuestionAnswer, Unit

from practice_app.session import (
    LESSON_LENGTH,
    ActiveExercise,
    Lesson,
    PracticeSession,
)


@pytest.fixture
def active() -> ActiveExercise:
    """One question, as the screen holds it."""
    return ActiveExercise(
        exercise=Exercise(
            id=1,
            exercise_id="1.1",
            exercise_number=1,
            unit=Unit(id=1, unit_number=12, title="Present Continuous"),
        ),
        question=Question(
            id=1,
            question_id="2",
            is_open_ended=False,
            section_letter="A",
            rule="Use present continuous",
        ),
        topic_id=1,
        topic_name="Present Tenses",
        answers=(
            QuestionAnswer(short_answer="is doing", full_answer="He **is doing** it."),
            QuestionAnswer(short_answer="'s doing", full_answer="He **'s doing** it."),
        ),
    )


class TestActiveExercise:
    def test_a_fresh_question_hides_its_answer(self, active: ActiveExercise) -> None:
        assert active.is_revealed is False
        assert active.revealed_answers == ()

    def test_revealing_shows_the_canonical_answer(self, active: ActiveExercise) -> None:
        active.ungraded = True

        assert active.is_revealed is True
        assert [answer.short_answer for answer in active.revealed_answers] == [
            "is doing"
        ]

    def test_grading_shows_what_the_grader_matched(
        self, active: ActiveExercise
    ) -> None:
        active.evaluation = EvaluateAnswerOutput(is_correct=True, answer_idx=[1])

        assert active.is_revealed is True
        assert [answer.short_answer for answer in active.revealed_answers] == [
            "'s doing"
        ]

    def test_the_unit_reference_joins_the_unit_and_the_section(
        self, active: ActiveExercise
    ) -> None:
        assert active.unit_reference == "12A"


class TestLesson:
    def test_a_new_run_starts_at_the_first_question(self) -> None:
        lesson = Lesson(topic_id=1, topic_name="Present Tenses")

        assert lesson.length == LESSON_LENGTH
        assert lesson.position == 1
        assert lesson.progress == 0.0
        assert lesson.accuracy == 0.0
        assert lesson.is_complete is False

    def test_answers_move_it_along(self) -> None:
        lesson = Lesson(topic_id=1, topic_name="Present Tenses", length=4)

        lesson.record(correct=True)
        lesson.record(correct=False)

        assert lesson.answered == 2
        assert lesson.correct == 1
        assert lesson.position == 3
        assert lesson.progress == 0.5
        assert lesson.accuracy == 0.5

    def test_the_last_answer_completes_it(self) -> None:
        lesson = Lesson(topic_id=None, topic_name="Mixed practice", length=2)

        lesson.record(correct=True)
        lesson.record(correct=True)

        assert lesson.is_complete is True
        assert lesson.progress == 1.0
        # The counter stops at the length rather than running past it.
        assert lesson.position == 2


class TestPracticeSession:
    def test_it_starts_with_nothing_open(self) -> None:
        session = PracticeSession()

        assert session.lesson is None
        assert session.active is None
        assert session.has_previous_topic is False

    def test_beginning_a_topic_run_remembers_the_topic(
        self, active: ActiveExercise
    ) -> None:
        session = PracticeSession()

        lesson = session.begin(1, "Present Tenses")
        lesson.active = active

        assert session.active is active
        assert session.has_previous_topic is True
        assert session.last_topic_name == "Present Tenses"

    def test_a_mixed_run_is_not_a_topic_to_return_to(self) -> None:
        session = PracticeSession()

        session.begin(None, "Mixed practice")

        assert session.has_previous_topic is False

    def test_ending_keeps_the_topic_for_next_time(self) -> None:
        session = PracticeSession()
        session.begin(1, "Present Tenses")

        session.end()

        assert session.lesson is None
        assert session.active is None
        assert session.last_topic_id == 1
