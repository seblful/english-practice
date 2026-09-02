"""SQLite access for practice content and bot authorization.

Every public method is ``async`` but SQLite is synchronous, so each query is
handed to a worker thread: a single exercise image is a few hundred kilobytes,
and reading one on the event loop would stall every other chat the bot is
holding. Connections are opened per query and always closed — ``with
sqlite3.connect(...)`` commits a transaction but, unlike most context managers,
does *not* close the connection.
"""

import asyncio
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

from english_practice.logging import get_logger
from english_practice.models.auth import AuthStatus, PendingUser
from english_practice.models.book import Exercise, Question, QuestionAnswer, Topic, Unit
from english_practice.settings import get_settings

logger = get_logger(__name__)

# Waiting beats failing when another writer holds the lock: bot writes are tiny.
_BUSY_TIMEOUT_SECONDS = 5.0

_EXERCISE_COLUMNS = """
    e.id, e.exercise_id, e.exercise_number,
    u.id AS unit_id, u.unit_number, u.title,
    (
        SELECT t.name
        FROM unit_topics ut
        JOIN topics t ON t.id = ut.topic_id
        WHERE ut.unit_id = u.id
        ORDER BY t.name
        LIMIT 1
    ) AS topic_name
"""

SqlParams = Sequence[Any]


def _to_exercise(row: sqlite3.Row, questions: Sequence[Question] = ()) -> Exercise:
    """Build an exercise from a joined exercise/unit row.

    Args:
        row: Row selected with ``_EXERCISE_COLUMNS``.
        questions: Questions belonging to the exercise, in display order.

    Returns:
        The exercise with its unit attached.
    """
    return Exercise(
        id=row["id"],
        exercise_id=row["exercise_id"],
        exercise_number=row["exercise_number"],
        unit=Unit(
            id=row["unit_id"],
            unit_number=row["unit_number"],
            title=row["title"],
            topic_name=row["topic_name"],
        ),
        questions=tuple(questions),
    )


class DatabaseRepository:
    """Reads practice content and records who may use the bot."""

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize the repository.

        Args:
            db_path: SQLite file to use. Defaults to the configured database.
        """
        self.db_path = db_path or get_settings().paths.database_path

    # ------------------------------------------------------------------
    # Plumbing
    # ------------------------------------------------------------------

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection that commits on success and always closes."""
        with closing(
            sqlite3.connect(self.db_path, timeout=_BUSY_TIMEOUT_SECONDS)
        ) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            with conn:  # commits on success, rolls back on exception
                yield conn

    def _query_sync(self, sql: str, params: SqlParams = ()) -> list[sqlite3.Row]:
        """Run a read query and return every row."""
        with self._connect() as conn:
            return conn.execute(sql, tuple(params)).fetchall()

    def _execute_sync(self, sql: str, params: SqlParams = ()) -> None:
        """Run a write statement."""
        with self._connect() as conn:
            conn.execute(sql, tuple(params))

    async def _rows(self, sql: str, params: SqlParams = ()) -> list[sqlite3.Row]:
        """Run a read query off the event loop.

        Args:
            sql: The statement to run.
            params: Bound parameters.

        Returns:
            Every matching row.
        """
        return await asyncio.to_thread(self._query_sync, sql, params)

    async def _row(self, sql: str, params: SqlParams = ()) -> sqlite3.Row | None:
        """Run a read query off the event loop and return the first row.

        Args:
            sql: The statement to run.
            params: Bound parameters.

        Returns:
            The first row, or ``None`` when there is none.
        """
        rows = await self._rows(sql, params)
        return rows[0] if rows else None

    async def _execute(self, sql: str, params: SqlParams = ()) -> None:
        """Run a write statement off the event loop.

        Args:
            sql: The statement to run.
            params: Bound parameters.
        """
        await asyncio.to_thread(self._execute_sync, sql, params)

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------

    async def list_topics(self) -> list[Topic]:
        """Return every topic, alphabetically, with its unit count.

        Returns:
            All topics in the database.
        """
        rows = await self._rows(
            """
            SELECT t.id, t.name, COUNT(ut.unit_id) AS unit_count
            FROM topics t
            LEFT JOIN unit_topics ut ON t.id = ut.topic_id
            GROUP BY t.id, t.name
            ORDER BY t.name
            """
        )
        return [Topic.model_validate(dict(row)) for row in rows]

    async def get_topic(self, topic_id: int) -> Topic | None:
        """Return one topic.

        Args:
            topic_id: Topic database ID.

        Returns:
            The topic, or ``None`` when no such topic exists.
        """
        row = await self._row(
            "SELECT id, name FROM topics WHERE id = ?",
            (topic_id,),
        )
        return Topic.model_validate(dict(row)) if row else None

    async def random_exercise(self, topic_id: int | None = None) -> Exercise | None:
        """Draw a random exercise that actually has questions.

        The ``EXISTS`` clause is what makes the draw safe to use directly: an
        exercise whose questions were never imported can never be returned, so
        callers need no retry loop. Selection happens in SQL rather than by
        loading every candidate row and choosing in Python.

        Args:
            topic_id: Restrict the draw to this topic, or ``None`` for any.

        Returns:
            An exercise with its questions, or ``None`` when the filter matches
            nothing.
        """
        topic_filter = (
            """
            AND EXISTS (
                SELECT 1 FROM unit_topics ut
                WHERE ut.unit_id = u.id AND ut.topic_id = ?
            )
            """
            if topic_id is not None
            else ""
        )
        row = await self._row(
            f"""
            SELECT {_EXERCISE_COLUMNS}
            FROM exercises e
            JOIN units u ON e.unit_id = u.id
            WHERE EXISTS (SELECT 1 FROM questions q WHERE q.exercise_id = e.id)
            {topic_filter}
            ORDER BY RANDOM()
            LIMIT 1
            """,
            () if topic_id is None else (topic_id,),
        )
        if row is None:
            return None
        return _to_exercise(row, await self._questions_for(row["id"]))

    async def _questions_for(self, exercise_id: int) -> list[Question]:
        """Return an exercise's questions in display order.

        Args:
            exercise_id: Exercise database ID.

        Returns:
            The questions, ordered as they are printed.
        """
        rows = await self._rows(
            """
            SELECT id, question_id, is_open_ended,
                   section_letter, rule, display_order
            FROM questions
            WHERE exercise_id = ?
            ORDER BY display_order, question_id
            """,
            (exercise_id,),
        )
        return [Question.model_validate(dict(row)) for row in rows]

    async def get_exercise_image(self, exercise_id: int) -> bytes | None:
        """Return an exercise's image bytes.

        Args:
            exercise_id: Exercise database ID.

        Returns:
            The stored PNG bytes, or ``None`` when the exercise has no usable
            image. A zero-length blob is a broken import rather than a
            picture — ``scripts/database/validate.py`` reports them — so it
            counts as absent instead of reaching Telegram as an empty photo.
        """
        row = await self._row(
            "SELECT image_data FROM exercise_images WHERE exercise_id = ?",
            (exercise_id,),
        )
        if row is None:
            return None
        image: bytes = row["image_data"]
        return image or None

    async def list_answers(self, question_id: int) -> list[QuestionAnswer]:
        """Return every accepted answer for a question.

        Args:
            question_id: Question database ID.

        Returns:
            The answers in insertion order; the first is the canonical one.
        """
        rows = await self._rows(
            """
            SELECT short_answer, full_answer
            FROM question_answers
            WHERE question_id = ?
            ORDER BY id
            """,
            (question_id,),
        )
        return [QuestionAnswer.model_validate(dict(row)) for row in rows]

    # ------------------------------------------------------------------
    # Authorization
    # ------------------------------------------------------------------

    async def get_auth_status(self, telegram_id: int) -> AuthStatus | None:
        """Return a user's authorization status.

        Args:
            telegram_id: Telegram user ID.

        Returns:
            The stored status, or ``None`` when the user is unknown.
        """
        row = await self._row(
            "SELECT status FROM authorized_users WHERE telegram_id = ?",
            (telegram_id,),
        )
        if row is None:
            return None
        status: AuthStatus = row["status"]
        return status

    async def register_user(
        self,
        telegram_id: int,
        full_name: str,
        telegram_username: str | None,
    ) -> None:
        """Record a new access request, leaving an existing one untouched.

        Args:
            telegram_id: Telegram user ID.
            full_name: Name reported by Telegram.
            telegram_username: Telegram @username, when the user has one.
        """
        await self._execute(
            """
            INSERT OR IGNORE INTO authorized_users
            (telegram_id, full_name, telegram_username)
            VALUES (?, ?, ?)
            """,
            (telegram_id, full_name, telegram_username),
        )

    async def set_auth_status(
        self,
        telegram_id: int,
        status: AuthStatus,
        handled_by: int,
    ) -> None:
        """Approve or reject a user.

        Args:
            telegram_id: Telegram user ID.
            status: The decision to record.
            handled_by: Telegram ID of the admin who decided.
        """
        await self._execute(
            """
            UPDATE authorized_users
            SET status = ?, handled_at = CURRENT_TIMESTAMP, handled_by = ?
            WHERE telegram_id = ?
            """,
            (status, handled_by, telegram_id),
        )

    async def reset_to_pending(
        self,
        telegram_id: int,
        full_name: str,
        telegram_username: str | None,
    ) -> None:
        """Put a previously rejected user back in the approval queue.

        Args:
            telegram_id: Telegram user ID.
            full_name: Name reported by Telegram, refreshed on re-application.
            telegram_username: Telegram @username, when the user has one.
        """
        await self._execute(
            """
            UPDATE authorized_users
            SET status = 'pending', full_name = ?, telegram_username = ?,
                handled_at = NULL, handled_by = NULL
            WHERE telegram_id = ?
            """,
            (full_name, telegram_username, telegram_id),
        )

    async def list_pending_users(self) -> list[PendingUser]:
        """Return everyone waiting for a decision, oldest request first.

        Returns:
            The pending access requests.
        """
        rows = await self._rows(
            """
            SELECT telegram_id, full_name, telegram_username, created_at
            FROM authorized_users
            WHERE status = 'pending'
            ORDER BY created_at ASC
            """
        )
        return [PendingUser.model_validate(dict(row)) for row in rows]
