"""Database repository for exercises and topics."""

import random
import sqlite3
from pathlib import Path

from config.settings import settings


class DatabaseRepository:
    """Repository for database operations."""

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize repository with database path.

        Args:
            db_path: Path to SQLite database. Uses default if not provided.
        """
        if db_path is None:
            db_path = settings.paths.content_dir / "english_practice.db"
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_all_topics(self) -> list[dict]:
        """Get all topics from database.

        Returns:
            List of topics with id and name.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT t.id, t.name, COUNT(ut.unit_id) as unit_count
                FROM topics t
                LEFT JOIN unit_topics ut ON t.id = ut.topic_id
                GROUP BY t.id, t.name
                ORDER BY t.name
                """
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_topic_by_id(self, topic_id: int) -> dict | None:
        """Get topic by ID.

        Args:
            topic_id: Topic ID.

        Returns:
            Topic dict or None if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, name FROM topics WHERE id = ?", (topic_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_random_exercise(self, topic_id: int | None = None) -> dict | None:
        """Get random exercise, optionally filtered by topic.

        Args:
            topic_id: Optional topic ID to filter by.

        Returns:
            Exercise dict or None if not found.
        """
        with self._get_connection() as conn:
            if topic_id:
                cursor = conn.execute(
                    """
                    SELECT e.id, e.exercise_id, e.exercise_number, e.image_path,
                           u.id as unit_id, u.unit_number, u.title
                    FROM exercises e
                    JOIN units u ON e.unit_id = u.id
                    JOIN unit_topics ut ON u.id = ut.unit_id
                    WHERE ut.topic_id = ?
                    """,
                    (topic_id,),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT e.id, e.exercise_id, e.exercise_number, e.image_path,
                           u.id as unit_id, u.unit_number, u.title
                    FROM exercises e
                    JOIN units u ON e.unit_id = u.id
                    """
                )

            exercises = [dict(row) for row in cursor.fetchall()]

            if not exercises:
                return None

            return random.choice(exercises)

    def get_exercise_with_questions(self, exercise_id: int) -> dict | None:
        """Get exercise with all its questions.

        Args:
            exercise_id: Exercise database ID.

        Returns:
            Exercise dict with questions list, or None if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT e.id, e.exercise_id, e.exercise_number, e.image_path,
                       u.id as unit_id, u.unit_number, u.title
                FROM exercises e
                JOIN units u ON e.unit_id = u.id
                WHERE e.id = ?
                """,
                (exercise_id,),
            )
            row = cursor.fetchone()

            if not row:
                return None

            exercise = dict(row)

            cursor = conn.execute(
                """
                SELECT id, question_id, correct_answer, display_order
                FROM questions
                WHERE exercise_id = ?
                ORDER BY display_order, question_id
                """,
                (exercise_id,),
            )

            exercise["questions"] = [dict(row) for row in cursor.fetchall()]
            return exercise

    def get_question_by_number(
        self, exercise_id: int, question_number: str
    ) -> dict | None:
        """Get specific question from exercise.

        Args:
            exercise_id: Exercise database ID.
            question_number: Question number (e.g., "5", "2a").

        Returns:
            Question dict or None if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, question_id, correct_answer, display_order
                FROM questions
                WHERE exercise_id = ? AND question_id = ?
                """,
                (exercise_id, question_number),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def check_answer(self, question_id: int, user_answer: str) -> tuple[bool, str]:
        """Check if user answer matches correct answer.

        Args:
            question_id: Question database ID.
            user_answer: User's answer.

        Returns:
            Tuple of (is_correct, correct_answer).
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT correct_answer FROM questions WHERE id = ?", (question_id,)
            )
            row = cursor.fetchone()

            if not row:
                return False, ""

            correct_answer = row["correct_answer"]

            normalized_user = user_answer.strip().lower()
            normalized_correct = correct_answer.strip().lower()

            is_correct = (
                normalized_user == normalized_correct
                or normalized_user in normalized_correct
                or normalized_correct in normalized_user
            )

            return is_correct, correct_answer

    def get_grammar_md_for_exercise(self, exercise_id: int) -> str | None:
        """Get grammar markdown content for an exercise.

        Args:
            exercise_id: Exercise database ID.

        Returns:
            Grammar markdown content or None if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT u.grammar_md_path
                FROM exercises e
                JOIN units u ON e.unit_id = u.id
                WHERE e.id = ?
                """,
                (exercise_id,),
            )
            row = cursor.fetchone()

            if not row or not row["grammar_md_path"]:
                return None

            md_path = settings.paths.content_dir / row["grammar_md_path"]
            if not md_path.exists():
                return None

            return md_path.read_text(encoding="utf-8")
