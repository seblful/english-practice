"""SQLite access to the practice content.

Every public method is ``async`` but SQLite is synchronous, so each query is
handed to a worker thread: a single exercise image is tens to hundreds of
kilobytes, and reading one on the event loop stalls every other chat the bot is
holding — and drops frames mid-animation on a phone.

Connections are opened per query and always closed. ``with sqlite3.connect(...)``
commits a transaction but, unlike most context managers, does *not* close the
connection.

The app opens the database read-only, because it ships inside the APK and
nothing may write to it; the bot opens it read-write, because it also keeps the
table of who is allowed to use it. That is the only difference, and it is a
constructor flag.
"""

import asyncio
import random
import sqlite3
from collections.abc import Callable, Iterator, Sequence
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

from practice_core.errors import ContentError
from practice_core.models import (
    ContentCounts,
    Exercise,
    Question,
    QuestionAnswer,
    Topic,
    Unit,
)

__all__ = ["ContentLibrary", "DrawnQuestion"]

# Waiting beats failing when another writer holds the lock: bot writes are tiny.
BUSY_TIMEOUT_SECONDS = 5.0

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

# An exercise, the question drawn from it, and its picture.
type DrawnQuestion = tuple[Exercise, Question, bytes | None]


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


class ContentLibrary:
    """Reads the book: topics, exercises, questions, answers and images."""

    def __init__(self, db_path: Path, *, read_only: bool = False) -> None:
        """Initialize the library.

        Args:
            db_path: SQLite file to use. It is not opened until the first
                query, so constructing this before the file exists is safe.
            read_only: Open the file read-only, and refuse to create it. The
                app sets this; the bot does not, because it also writes.
        """
        self.db_path = db_path
        self.read_only = read_only

    # ------------------------------------------------------------------
    # Plumbing
    # ------------------------------------------------------------------

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection that commits on success and always closes.

        Yields:
            A connection with row access by column name.

        Raises:
            ContentError: If the database cannot be opened. Read-only mode
                checks for the file first: SQLite's own message for a missing
                file is "unable to open database file", which tells a user
                nothing about what to do next.
        """
        if self.read_only and not self.db_path.exists():
            raise ContentError(f"The exercise database is missing at {self.db_path}.")

        try:
            with closing(self._open()) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys = ON")
                with conn:  # commits on success, rolls back on exception
                    yield conn
        except sqlite3.Error as exc:
            raise ContentError(
                f"The exercise database could not be read: {exc}"
            ) from exc

    def _open(self) -> sqlite3.Connection:
        """Open the database, honouring :attr:`read_only`."""
        if self.read_only:
            return sqlite3.connect(
                f"file:{self.db_path.as_posix()}?mode=ro",
                uri=True,
                timeout=BUSY_TIMEOUT_SECONDS,
            )
        return sqlite3.connect(self.db_path, timeout=BUSY_TIMEOUT_SECONDS)

    def _query_sync(self, sql: str, params: SqlParams = ()) -> list[sqlite3.Row]:
        """Run a read query and return every row."""
        with self._connect() as conn:
            return conn.execute(sql, tuple(params)).fetchall()

    def _execute_sync(self, sql: str, params: SqlParams = ()) -> None:
        """Run a write statement."""
        with self._connect() as conn:
            conn.execute(sql, tuple(params))

    def _script_sync(self, sql: str) -> None:
        """Run a multi-statement script."""
        with self._connect() as conn:
            conn.executescript(sql)

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

    async def _script(self, sql: str) -> None:
        """Run a multi-statement script off the event loop.

        Args:
            sql: The statements to run, semicolon-separated. Callers pass
                schema text, which is why this takes no parameters.
        """
        await asyncio.to_thread(self._script_sync, sql)

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------

    async def counts(self) -> ContentCounts:
        """Return how much material the database holds.

        Returns:
            The row counts, for an "about" screen or a health check.
        """
        row = await self._row(
            """
            SELECT
                (SELECT COUNT(*) FROM topics) AS topics,
                (SELECT COUNT(*) FROM units) AS units,
                (SELECT COUNT(*) FROM exercises) AS exercises,
                (SELECT COUNT(*) FROM questions) AS questions
            """
        )
        if row is None:  # pragma: no cover - a bare aggregate always returns a row
            return ContentCounts(topics=0, units=0, exercises=0, questions=0)
        return ContentCounts.model_validate(dict(row))

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
            """
            SELECT t.id, t.name, COUNT(ut.unit_id) AS unit_count
            FROM topics t
            LEFT JOIN unit_topics ut ON t.id = ut.topic_id
            WHERE t.id = ?
            GROUP BY t.id, t.name
            """,
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
            The stored image, or ``None`` when the exercise has no usable one.
            A zero-length blob is a broken import rather than a picture —
            :mod:`practice_extraction.validate` reports them — so it counts as
            absent instead of reaching a screen as an empty frame.
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

    async def draw_question(
        self,
        topic_id: int | None = None,
        *,
        choose: Callable[[Sequence[Question]], Question] | None = None,
    ) -> DrawnQuestion | None:
        """Draw an exercise, pick one of its questions, and load its image.

        Doing all three together is what keeps a caller from holding a
        half-drawn exercise: either there is something to practise or there is
        not.

        Args:
            topic_id: Restrict the draw to this topic, or ``None`` for any.
            choose: Random source for picking the question, injectable so a
                test can make the draw deterministic.

        Returns:
            The exercise, the question to answer, and the exercise image, or
            ``None`` when the filter matches nothing to practise.
        """
        exercise = await self.random_exercise(topic_id)
        if exercise is None or not exercise.questions:
            return None
        picker = choose or random.choice
        question = picker(exercise.questions)
        return exercise, question, await self.get_exercise_image(exercise.id)
