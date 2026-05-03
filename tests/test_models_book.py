"""Tests for domain Pydantic models."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.english_practice.models.book import Exercise, Question, QuestionAnswer, Topic, Unit


class TestUnit:
    """Tests for Unit model."""

    def test_minimal(self) -> None:
        unit = Unit(unit_number=1, title="Present Tenses", grammar_md_path="grammar/1.md")
        assert unit.unit_number == 1
        assert unit.title == "Present Tenses"

    def test_validates_path_from_string(self) -> None:
        unit = Unit(unit_number=1, title="Test", grammar_md_path="grammar/1.md")
        assert isinstance(unit.grammar_md_path, Path)

    def test_validates_path_from_path(self) -> None:
        unit = Unit(unit_number=1, title="Test", grammar_md_path=Path("grammar/1.md"))
        assert isinstance(unit.grammar_md_path, Path)

    def test_negative_unit_number(self) -> None:
        with pytest.raises(ValidationError):
            Unit(unit_number=-1, title="Test", grammar_md_path="grammar/1.md")

    def test_zero_unit_number(self) -> None:
        with pytest.raises(ValidationError):
            Unit(unit_number=0, title="Test", grammar_md_path="grammar/1.md")


class TestExercise:
    """Tests for Exercise model."""

    def test_minimal(self) -> None:
        ex = Exercise(exercise_id="1.1", exercise_number=1)
        assert ex.exercise_id == "1.1"
        assert ex.exercise_number == 1
        assert ex.image_path is None

    def test_with_image_path_string(self) -> None:
        ex = Exercise(
            exercise_id="1.1",
            exercise_number=1,
            image_path="exercises/1/1.1.png",
        )
        assert isinstance(ex.image_path, Path)

    def test_with_image_path_path(self) -> None:
        ex = Exercise(
            exercise_id="1.1",
            exercise_number=1,
            image_path=Path("exercises/1/1.1.png"),
        )
        assert isinstance(ex.image_path, Path)


class TestQuestion:
    """Tests for Question model."""

    def test_minimal(self) -> None:
        q = Question(question_id="1")
        assert q.question_id == "1"
        assert q.is_open_ended is False
        assert q.section_letter is None
        assert q.rule is None
        assert q.display_order == 0

    def test_full(self) -> None:
        q = Question(
            question_id="2a",
            is_open_ended=True,
            section_letter="B",
            rule="Use past tense",
            display_order=3,
        )
        assert q.is_open_ended is True
        assert q.section_letter == "B"
        assert q.display_order == 3


class TestQuestionAnswer:
    """Tests for QuestionAnswer model."""

    def test_fields(self) -> None:
        qa = QuestionAnswer(
            short_answer="is doing",
            full_answer="He **is doing** his homework.",
        )
        assert qa.short_answer == "is doing"
        assert "is doing" in qa.full_answer


class TestTopic:
    """Tests for Topic model."""

    def test_minimal(self) -> None:
        t = Topic(name="Present Tenses")
        assert t.name == "Present Tenses"

    def test_empty_name(self) -> None:
        t = Topic(name="")
        assert t.name == ""
