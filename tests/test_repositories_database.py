"""Tests for the SQLite repository, against a real database file."""

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from english_practice.repositories.database import DatabaseRepository
from english_practice.settings import Settings


@pytest.fixture
def db_path(seeded_db_path: Path) -> Path:
    """The seeded database, under the name these tests use."""
    return seeded_db_path


@pytest.fixture
def repository(db_path: Path) -> DatabaseRepository:
    """A repository pointed at the seeded database."""
    return DatabaseRepository(db_path)


class TestTopics:
    """Tests for reading topics."""

    async def test_lists_topics_alphabetically_with_unit_counts(
        self, repository: DatabaseRepository
    ) -> None:
        topics = await repository.list_topics()

        assert [topic.name for topic in topics] == [
            "Past Tenses",
            "Present Tenses",
            "Unused Topic",
        ]
        assert {topic.name: topic.unit_count for topic in topics}["Present Tenses"] == 1

    async def test_gets_one_topic(self, repository: DatabaseRepository) -> None:
        topic = await repository.get_topic(1)

        assert topic is not None
        assert topic.name == "Present Tenses"

    async def test_unknown_topic(self, repository: DatabaseRepository) -> None:
        assert await repository.get_topic(404) is None


class TestExercises:
    """Tests for drawing and reading exercises."""

    async def test_random_draw_respects_the_topic(
        self, repository: DatabaseRepository
    ) -> None:
        for _ in range(10):
            exercise = await repository.random_exercise(topic_id=2)

            assert exercise is not None
            assert exercise.unit.unit_number == 2

    async def test_random_draw_never_returns_a_questionless_exercise(
        self, repository: DatabaseRepository
    ) -> None:
        """Exercise 2 has no questions, so the draw must skip it."""
        for _ in range(20):
            exercise = await repository.random_exercise(topic_id=1)

            assert exercise is not None
            assert exercise.id == 1
            assert exercise.questions

    async def test_random_draw_from_all_topics(
        self, repository: DatabaseRepository
    ) -> None:
        exercise = await repository.random_exercise()

        assert exercise is not None
        assert exercise.id in {1, 3}

    async def test_empty_topic_yields_nothing(
        self, repository: DatabaseRepository
    ) -> None:
        assert await repository.random_exercise(topic_id=3) is None

    async def test_exercise_carries_its_unit_and_topic(
        self, repository: DatabaseRepository
    ) -> None:
        exercise = await repository.random_exercise(topic_id=1)

        assert exercise is not None
        assert exercise.exercise_id == "1.1"
        assert exercise.unit.title == "Present Continuous"
        assert exercise.unit.topic_name == "Present Tenses"

    async def test_questions_come_back_in_display_order(
        self, repository: DatabaseRepository
    ) -> None:
        exercise = await repository.random_exercise(topic_id=1)

        assert exercise is not None
        assert [q.question_id for q in exercise.questions] == ["1", "2"]

    async def test_question_fields_are_typed(
        self, repository: DatabaseRepository
    ) -> None:
        exercise = await repository.random_exercise(topic_id=1)

        assert exercise is not None
        open_ended, closed = exercise.questions
        assert open_ended.is_open_ended is True
        assert open_ended.rule is None
        assert closed.is_open_ended is False
        assert closed.rule == "Use present continuous"

    async def test_exercise_image(self, repository: DatabaseRepository) -> None:
        assert await repository.get_exercise_image(1) == b"\x89PNG"

    async def test_missing_exercise_image(self, repository: DatabaseRepository) -> None:
        assert await repository.get_exercise_image(2) is None

    async def test_zero_length_image_counts_as_absent(
        self, repository: DatabaseRepository, db_path: Path
    ) -> None:
        """A broken import stores an empty blob; it must not reach Telegram."""
        with closing(sqlite3.connect(db_path)) as conn, conn:
            conn.execute(
                "UPDATE exercise_images SET image_data = ? WHERE exercise_id = 1",
                (b"",),
            )

        assert await repository.get_exercise_image(1) is None


class TestAnswers:
    """Tests for reading a question's answers."""

    async def test_lists_answers_in_insertion_order(
        self, repository: DatabaseRepository
    ) -> None:
        answers = await repository.list_answers(1)

        assert [answer.short_answer for answer in answers] == ["is doing", "'s doing"]
        assert answers[0].full_answer == "He is doing."

    async def test_question_without_answers(
        self, repository: DatabaseRepository
    ) -> None:
        assert await repository.list_answers(2) == []


class TestAuthorization:
    """Tests for the access-control tables."""

    async def test_unknown_user_has_no_status(
        self, repository: DatabaseRepository
    ) -> None:
        assert await repository.get_auth_status(1) is None

    async def test_registering_starts_as_pending(
        self, repository: DatabaseRepository
    ) -> None:
        await repository.register_user(1, "Alice", "alice")

        assert await repository.get_auth_status(1) == "pending"

    async def test_registering_twice_keeps_the_first_record(
        self, repository: DatabaseRepository
    ) -> None:
        await repository.register_user(1, "Alice", "alice")
        await repository.set_auth_status(1, "approved", handled_by=9)
        await repository.register_user(1, "Alice", "alice")

        assert await repository.get_auth_status(1) == "approved"

    async def test_approving_and_rejecting(
        self, repository: DatabaseRepository
    ) -> None:
        await repository.register_user(1, "Alice", None)

        await repository.set_auth_status(1, "approved", handled_by=9)
        assert await repository.get_auth_status(1) == "approved"

        await repository.set_auth_status(1, "rejected", handled_by=9)
        assert await repository.get_auth_status(1) == "rejected"

    async def test_reset_to_pending_clears_the_decision(
        self, repository: DatabaseRepository, db_path: Path
    ) -> None:
        await repository.register_user(1, "Alice", "alice")
        await repository.set_auth_status(1, "rejected", handled_by=9)

        await repository.reset_to_pending(1, "Alice Updated", "alice2")

        assert await repository.get_auth_status(1) == "pending"
        with closing(sqlite3.connect(db_path)) as conn, conn:
            row = conn.execute(
                "SELECT full_name, telegram_username, handled_at, handled_by "
                "FROM authorized_users WHERE telegram_id = 1"
            ).fetchone()
        assert row == ("Alice Updated", "alice2", None, None)

    async def test_pending_queue_is_oldest_first_and_excludes_decided(
        self, repository: DatabaseRepository, db_path: Path
    ) -> None:
        with closing(sqlite3.connect(db_path)) as conn, conn:
            conn.executescript(
                """
                INSERT INTO authorized_users
                    (telegram_id, full_name, telegram_username, status, created_at)
                VALUES (1, 'Alice', 'alice', 'pending', '2026-01-01'),
                       (2, 'Bob', NULL, 'pending', '2026-01-02'),
                       (3, 'Carol', NULL, 'approved', '2026-01-03');
                """
            )

        pending = await repository.list_pending_users()

        assert [user.full_name for user in pending] == ["Alice", "Bob"]
        assert pending[0].label == "Alice (@alice)"
        assert pending[1].label == "Bob"


class TestConnectionHandling:
    """A bot that leaks connections dies slowly; assert it does not."""

    async def test_connections_are_closed(
        self, repository: DatabaseRepository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`with sqlite3.connect(...)` commits but does not close — so we must."""
        opened = 0
        closed = 0
        real_connect = sqlite3.connect

        class TrackingConnection(sqlite3.Connection):
            def close(self) -> None:
                nonlocal closed
                closed += 1
                super().close()

        def tracking_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
            nonlocal opened
            opened += 1
            kwargs["factory"] = TrackingConnection
            return real_connect(*args, **kwargs)

        monkeypatch.setattr(sqlite3, "connect", tracking_connect)

        await repository.list_topics()
        await repository.register_user(1, "Alice", None)

        assert opened == 2
        assert closed == opened

    async def test_write_is_committed(self, repository: DatabaseRepository) -> None:
        await repository.register_user(1, "Alice", None)

        # A fresh repository sees only committed data.
        assert await DatabaseRepository(repository.db_path).get_auth_status(1) == (
            "pending"
        )

    async def test_defaults_to_the_configured_database(
        self, monkeypatch: pytest.MonkeyPatch, db_path: Path
    ) -> None:
        settings = Settings()
        settings.paths.database_path = db_path
        monkeypatch.setattr(
            "english_practice.repositories.database.get_settings", lambda: settings
        )

        assert DatabaseRepository().db_path == db_path
