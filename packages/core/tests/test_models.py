"""Tests for the shared content models."""

import pytest
from pydantic import ValidationError

from practice_core.models import Exercise, Question, QuestionAnswer, Topic, Unit


class TestUnit:
    def test_a_unit_outside_any_topic(self) -> None:
        assert Unit(id=1, unit_number=3, title="Present Perfect").topic_name is None

    def test_a_unit_number_starts_at_one(self) -> None:
        with pytest.raises(ValidationError):
            Unit(id=1, unit_number=0, title="Nowhere")


class TestQuestion:
    def test_a_rule_that_is_present(self, question: Question) -> None:
        assert question.has_rule is True

    @pytest.mark.parametrize("rule", [None, "", "   "])
    def test_a_rule_that_is_not(self, rule: str | None) -> None:
        """Whitespace is what the extraction pipeline leaves for "no rule"."""
        assert Question(id=1, question_id="1", rule=rule).has_rule is False

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

    def test_defaults_to_no_questions(self, unit: Unit) -> None:
        exercise = Exercise(id=1, exercise_id="1.1", exercise_number=1, unit=unit)

        assert exercise.questions == ()

    def test_requires_a_unit(self) -> None:
        with pytest.raises(ValidationError):
            Exercise.model_validate(
                {"id": 1, "exercise_id": "1.1", "exercise_number": 1}
            )


class TestQuestionAnswer:
    def test_carries_both_forms_of_the_answer(self) -> None:
        answer = QuestionAnswer(
            short_answer="He's tying", full_answer="Look. **He's tying** his shoes."
        )

        assert answer.short_answer == "He's tying"

    def test_both_parts_are_required(self) -> None:
        with pytest.raises(ValidationError):
            QuestionAnswer.model_validate({"short_answer": "only"})


class TestTopic:
    def test_unit_count_defaults_to_zero(self) -> None:
        assert Topic(id=1, name="Present Tenses").unit_count == 0

    def test_a_topic_cannot_cover_negative_units(self) -> None:
        with pytest.raises(ValidationError):
            Topic(id=1, name="Broken", unit_count=-1)


class TestImmutability:
    def test_a_drawn_exercise_cannot_be_edited(self, exercise: Exercise) -> None:
        """These are read models; a screen holding one must not mutate it."""
        with pytest.raises(ValidationError):
            exercise.exercise_id = "9.9"  # ty: ignore[invalid-assignment]

    def test_a_unit_cannot_be_edited(self, unit: Unit) -> None:
        # setattr, not `unit.title = ...`: the latter is a static type error,
        # and the point here is the runtime guarantee.
        with pytest.raises(ValidationError):
            setattr(unit, "title", "Changed")  # noqa: B010
