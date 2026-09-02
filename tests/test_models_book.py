"""Tests for the practice-content models."""

import pytest
from pydantic import ValidationError

from english_practice.models.auth import PendingUser
from english_practice.models.book import Exercise, Question, QuestionAnswer, Topic, Unit


class TestUnit:
    """Tests for the unit model."""

    def test_valid(self) -> None:
        unit = Unit(id=1, unit_number=3, title="Present Perfect")

        assert unit.topic_name is None

    def test_unit_number_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            Unit(id=1, unit_number=0, title="Nope")

    def test_is_immutable(self) -> None:
        unit = Unit(id=1, unit_number=1, title="Present Perfect")

        # setattr, not `unit.title = ...`: the latter is a static type error,
        # and the point here is the runtime guarantee.
        with pytest.raises(ValidationError):
            setattr(unit, "title", "Changed")  # noqa: B010


class TestQuestion:
    """Tests for the question model."""

    def test_defaults(self) -> None:
        question = Question(id=1, question_id="2")

        assert question.is_open_ended is False
        assert question.section_letter is None
        assert question.rule is None
        assert question.display_order == 0

    def test_coerces_sqlite_integers_to_booleans(self) -> None:
        """SQLite stores booleans as 0/1."""
        assert Question(id=1, question_id="2", is_open_ended=1).is_open_ended is True

    def test_accepts_lettered_question_numbers(self) -> None:
        assert Question(id=1, question_id="10 b").question_id == "10 b"


class TestExercise:
    """Tests for the exercise model."""

    def test_carries_its_unit_and_questions(self, unit: Unit) -> None:
        exercise = Exercise(
            id=1,
            exercise_id="1.1",
            exercise_number=1,
            unit=unit,
            questions=(Question(id=1, question_id="1"),),
        )

        assert exercise.unit.unit_number == 1
        assert len(exercise.questions) == 1

    def test_questions_default_to_empty(self, unit: Unit) -> None:
        exercise = Exercise(id=1, exercise_id="1.1", exercise_number=1, unit=unit)

        assert exercise.questions == ()

    def test_requires_a_unit(self) -> None:
        with pytest.raises(ValidationError):
            Exercise.model_validate(
                {"id": 1, "exercise_id": "1.1", "exercise_number": 1}
            )


class TestQuestionAnswer:
    """Tests for the answer model."""

    def test_valid(self) -> None:
        answer = QuestionAnswer(
            short_answer="He's tying", full_answer="Look. **He's tying** his shoes."
        )

        assert answer.short_answer == "He's tying"

    def test_both_parts_are_required(self) -> None:
        with pytest.raises(ValidationError):
            QuestionAnswer.model_validate({"short_answer": "only"})


class TestTopic:
    """Tests for the topic model."""

    def test_unit_count_defaults_to_zero(self) -> None:
        assert Topic(id=1, name="Present Tenses").unit_count == 0

    def test_unit_count_cannot_be_negative(self) -> None:
        with pytest.raises(ValidationError):
            Topic(id=1, name="Present Tenses", unit_count=-1)


class TestPendingUser:
    """Tests for the access-request model."""

    def test_label_includes_the_username(self) -> None:
        user = PendingUser(telegram_id=1, full_name="Alice", telegram_username="alice")

        assert user.label == "Alice (@alice)"

    def test_label_without_a_username(self) -> None:
        assert PendingUser(telegram_id=1, full_name="Alice").label == "Alice"
