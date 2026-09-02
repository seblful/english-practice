"""Tests for the shared content models."""

import pytest
from pydantic import ValidationError

from practice_core.models import Exercise, Question, Topic, Unit


class TestQuestion:
    def test_a_rule_that_is_present(self, question: Question) -> None:
        assert question.has_rule is True

    @pytest.mark.parametrize("rule", [None, "", "   "])
    def test_a_rule_that_is_not(self, rule: str | None) -> None:
        """Whitespace is what the extraction pipeline leaves for "no rule"."""
        assert Question(id=1, question_id="1", rule=rule).has_rule is False


class TestImmutability:
    def test_a_drawn_exercise_cannot_be_edited(self, exercise: Exercise) -> None:
        """These are read models; a screen holding one must not mutate it."""
        with pytest.raises(ValidationError):
            exercise.exercise_id = "9.9"  # ty: ignore[invalid-assignment]


class TestValidation:
    def test_a_unit_number_starts_at_one(self) -> None:
        with pytest.raises(ValidationError):
            Unit(id=1, unit_number=0, title="Nowhere")

    def test_a_topic_cannot_cover_negative_units(self) -> None:
        with pytest.raises(ValidationError):
            Topic(id=1, name="Broken", unit_count=-1)

    def test_an_exercise_defaults_to_no_questions(self, unit: Unit) -> None:
        exercise = Exercise(id=1, exercise_id="1.1", exercise_number=1, unit=unit)

        assert exercise.questions == ()
