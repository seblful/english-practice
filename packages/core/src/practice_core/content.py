"""Reading the book: topics, exercises, questions, answers and images.

Every public method is ``async``. Running the statement off the event loop is
:class:`~practice_core.sqlite.SqliteStore`'s job, and this holds one rather
than being one -- the bot keeps its own table of authorized users in the same
file, and it used to reach that plumbing by subclassing this class, so a table
that has nothing to do with the book came with every content query attached.

The app opens the database read-only, because it ships inside the APK and
nothing may write to it; the bot opens it read-write. That is the only
difference, and it is a constructor flag.
"""

import random
import sqlite3
from collections.abc import Callable, Sequence
from pathlib import Path

from practice_core.lesson import ActiveExercise, topic_label
from practice_core.models import (
    ContentCounts,
    Exercise,
    Question,
    QuestionAnswer,
    Topic,
    Unit,
)
from practice_core.sqlite import SqliteStore

__all__ = ["ContentLibrary"]

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
        self._store = SqliteStore(db_path, read_only=read_only)

    @property
    def db_path(self) -> Path:
        """Return the file this library reads."""
        return self._store.db_path

    @property
    def read_only(self) -> bool:
        """Whether this library refuses to write."""
        return self._store.read_only

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------

    async def counts(self) -> ContentCounts:
        """Return how much material the database holds.

        Returns:
            The row counts, for an "about" screen or a health check.
        """
        row = await self._store.row(
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
        rows = await self._store.rows(
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
        row = await self._store.row(
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
        row = await self._store.row(
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
        rows = await self._store.rows(
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
        row = await self._store.row(
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
        rows = await self._store.rows(
            """
            SELECT short_answer, full_answer
            FROM question_answers
            WHERE question_id = ?
            ORDER BY id
            """,
            (question_id,),
        )
        return [QuestionAnswer.model_validate(dict(row)) for row in rows]

    async def draw(
        self,
        topic_id: int | None = None,
        *,
        topic_name: str | None = None,
        choose: Callable[[Sequence[Question]], Question] | None = None,
    ) -> ActiveExercise | None:
        """Draw a question a student can be asked, ready to be answered.

        Everything the question needs travels with it: the exercise it came
        from, its picture, the book's answers, and what to call the topic on
        screen. This used to hand back three of those as a tuple and leave the
        answers to the caller, so both front ends assembled the state
        themselves and the bot's copy went out with none -- an exercise whose
        reveal would have printed nothing had anything else reached it first.

        Args:
            topic_id: Restrict the draw to this topic, or ``None`` for any.
            topic_name: What the student called the topic they asked for.
                Ignored when no topic was asked for, so the label falls back
                to the unit -- the rule was spelled once per front end.
            choose: Random source for picking the question, injectable so a
                test can make the draw deterministic.

        Returns:
            The question and everything needed to ask and grade it, or
            ``None`` when the filter matches nothing to practise.
        """
        exercise = await self.random_exercise(topic_id)
        if exercise is None or not exercise.questions:
            return None
        picker = choose or random.choice
        question = picker(exercise.questions)
        return ActiveExercise(
            exercise=exercise,
            question=question,
            topic_id=topic_id,
            topic_name=topic_label(
                topic_name=topic_name if topic_id is not None else None,
                unit=exercise.unit,
            ),
            image=await self.get_exercise_image(exercise.id),
            answers=tuple(await self.list_answers(question.id)),
        )
