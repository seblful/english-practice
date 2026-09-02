"""Tests for the shared content library, against a real database file."""

import sqlite3
from collections.abc import Sequence
from pathlib import Path

import pytest

from practice_core.content import ContentLibrary
from practice_core.errors import ContentError
from practice_core.models import Question


class TestCounts:
    async def test_reports_what_the_database_holds(
        self, library: ContentLibrary
    ) -> None:
        counts = await library.counts()

        assert counts.topics == 3
        assert counts.units == 2
        assert counts.exercises == 3
        assert counts.questions == 3


class TestTopics:
    async def test_lists_topics_alphabetically_with_unit_counts(
        self, library: ContentLibrary
    ) -> None:
        topics = await library.list_topics()

        assert [topic.name for topic in topics] == [
            "Past Tenses",
            "Present Tenses",
            "Unused Topic",
        ]
        assert {topic.name: topic.unit_count for topic in topics} == {
            "Past Tenses": 1,
            "Present Tenses": 1,
            "Unused Topic": 0,
        }

    async def test_gets_one_topic_with_its_unit_count(
        self, library: ContentLibrary
    ) -> None:
        topic = await library.get_topic(1)

        assert topic is not None
        assert topic.name == "Present Tenses"
        assert topic.unit_count == 1

    async def test_unknown_topic(self, library: ContentLibrary) -> None:
        assert await library.get_topic(404) is None


class TestExercises:
    async def test_random_draw_respects_the_topic(
        self, library: ContentLibrary
    ) -> None:
        for _ in range(10):
            exercise = await library.random_exercise(topic_id=2)

            assert exercise is not None
            assert exercise.unit.unit_number == 2

    async def test_random_draw_never_returns_an_exercise_without_questions(
        self, library: ContentLibrary
    ) -> None:
        """Exercise 2 has none, so the draw must skip it every time."""
        for _ in range(25):
            exercise = await library.random_exercise()

            assert exercise is not None
            assert exercise.questions
            assert exercise.exercise_id != "1.2"

    async def test_a_topic_with_no_units_draws_nothing(
        self, library: ContentLibrary
    ) -> None:
        assert await library.random_exercise(topic_id=3) is None

    async def test_questions_arrive_in_display_order(
        self, library: ContentLibrary
    ) -> None:
        exercise = await library.random_exercise(topic_id=1)

        assert exercise is not None
        assert [q.question_id for q in exercise.questions] == ["1", "2"]

    async def test_the_units_primary_topic_travels_with_the_exercise(
        self, library: ContentLibrary
    ) -> None:
        exercise = await library.random_exercise(topic_id=1)

        assert exercise is not None
        assert exercise.unit.topic_name == "Present Tenses"


class TestImages:
    async def test_returns_the_stored_bytes(self, library: ContentLibrary) -> None:
        assert await library.get_exercise_image(1) == b"\x89PNG"

    async def test_an_exercise_without_a_row(self, library: ContentLibrary) -> None:
        assert await library.get_exercise_image(2) is None

    async def test_an_empty_blob_counts_as_absent(
        self, library: ContentLibrary
    ) -> None:
        """A zero-length blob is a broken import, not a picture."""
        assert await library.get_exercise_image(3) is None


class TestAnswers:
    async def test_lists_every_accepted_answer_in_order(
        self, library: ContentLibrary
    ) -> None:
        answers = await library.list_answers(1)

        assert [answer.short_answer for answer in answers] == ["is doing", "'s doing"]
        assert answers[0].full_answer == "He is doing."

    async def test_a_question_without_answers(self, library: ContentLibrary) -> None:
        assert await library.list_answers(2) == []


class TestDrawQuestion:
    async def test_draws_an_exercise_a_question_and_its_image(
        self, library: ContentLibrary
    ) -> None:
        drawn = await library.draw_question(topic_id=1)

        assert drawn is not None
        exercise, question, image = drawn
        assert exercise.exercise_id == "1.1"
        assert question in exercise.questions
        assert image == b"\x89PNG"

    async def test_the_question_picker_is_injectable(
        self, library: ContentLibrary
    ) -> None:
        def first(questions: Sequence[Question]) -> Question:
            return questions[0]

        drawn = await library.draw_question(topic_id=1, choose=first)

        assert drawn is not None
        assert drawn[1].question_id == "1"

    async def test_an_empty_topic_draws_nothing(self, library: ContentLibrary) -> None:
        assert await library.draw_question(topic_id=3) is None

    async def test_an_exercise_without_questions_is_never_drawn(
        self, tmp_path: Path, library: ContentLibrary
    ) -> None:
        """Emptying the only usable exercise leaves nothing to practise."""
        with sqlite3.connect(library.db_path) as conn:
            conn.execute("DELETE FROM questions")

        assert await library.draw_question() is None


class TestReadOnlyMode:
    async def test_reads_the_same_content(
        self, read_only_library: ContentLibrary
    ) -> None:
        assert len(await read_only_library.list_topics()) == 3

    async def test_refuses_to_write(self, read_only_library: ContentLibrary) -> None:
        with pytest.raises(ContentError, match="could not be read"):
            await read_only_library._execute("DELETE FROM topics")

    async def test_a_missing_file_names_itself(self, tmp_path: Path) -> None:
        library = ContentLibrary(tmp_path / "absent.db", read_only=True)

        with pytest.raises(ContentError, match=r"absent.db"):
            await library.list_topics()

    async def test_a_file_that_is_not_a_database(self, tmp_path: Path) -> None:
        broken = tmp_path / "broken.db"
        broken.write_text("not a database", encoding="utf-8")
        library = ContentLibrary(broken, read_only=True)

        with pytest.raises(ContentError, match="could not be read"):
            await library.list_topics()
