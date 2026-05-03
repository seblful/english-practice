"""Database repository for exercises and topics."""

import random
import sqlite3
from pathlib import Path

from config.settings import settings
from src.english_practice.models.book import QuestionAnswer


class DatabaseRepository:
    """Repository for database operations."""

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize repository with database path.

        Args:
            db_path: Path to SQLite database. Uses default if not provided.
        """
        self.db_path = db_path or settings.paths.database_path or settings.paths.data_dir / "development.db"

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
                    SELECT e.id, e.exercise_id, e.exercise_number,
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
                    SELECT e.id, e.exercise_id, e.exercise_number,
                           u.id as unit_id, u.unit_number, u.title
                    FROM exercises e
                    JOIN units u ON e.unit_id = u.id
                    """
                )

            exercises = [dict(row) for row in cursor.fetchall()]

            if not exercises:
                return None

            return random.choice(exercises)

    def get_exercise_image(self, exercise_id: int) -> bytes | None:
        """Get exercise image bytes from database.

        Args:
            exercise_id: Exercise database ID.

        Returns:
            Image bytes or None if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT image_data FROM exercise_images WHERE exercise_id = ?",
                (exercise_id,),
            )
            row = cursor.fetchone()
            return row["image_data"] if row else None

    def get_exercise_with_questions(self, exercise_id: int) -> dict | None:
        """Get exercise with all its questions.

        Args:
            exercise_id: Exercise database ID.

        Returns:
            Exercise dict with questions list, or None if not found.
        """
        with self._get_connection() as conn:
            exercise_row = conn.execute(
                """
                SELECT e.id, e.exercise_id, e.exercise_number,
                       u.id as unit_id, u.unit_number, u.title
                FROM exercises e
                JOIN units u ON e.unit_id = u.id
                WHERE e.id = ?
                """,
                (exercise_id,),
            ).fetchone()

            if not exercise_row:
                return None

            questions_rows = conn.execute(
                """
                SELECT id, question_id, is_open_ended, section_letter, rule, display_order
                FROM questions
                WHERE exercise_id = ?
                ORDER BY display_order, question_id
                """,
                (exercise_id,),
            ).fetchall()

            answers_rows = conn.execute(
                """
                SELECT question_id, short_answer, full_answer
                FROM question_answers
                WHERE question_id IN (SELECT id FROM questions WHERE exercise_id = ?)
                """,
                (exercise_id,),
            ).fetchall()

            answers_map: dict[int, list[dict]] = {}
            for row in answers_rows:
                q_id = row["question_id"]
                if q_id not in answers_map:
                    answers_map[q_id] = []
                answers_map[q_id].append(
                    {
                        "short_answer": row["short_answer"],
                        "full_answer": row["full_answer"],
                    }
                )

            questions = []
            for row in questions_rows:
                questions.append(
                    {
                        "id": row["id"],
                        "question_id": row["question_id"],
                        "is_open_ended": bool(row["is_open_ended"]),
                        "section_letter": row["section_letter"],
                        "rule": row["rule"],
                        "display_order": row["display_order"],
                        "answers": answers_map.get(row["id"], []),
                    }
                )

            return {
                **dict(exercise_row),
                "questions": questions,
            }

    def get_all_answers(self, question_id: int) -> list[QuestionAnswer]:
        """Get all answer variants for a question.

        Args:
            question_id: Question database ID.

        Returns:
            List of QuestionAnswer objects.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT short_answer, full_answer
                FROM question_answers
                WHERE question_id = ?
                """,
                (question_id,),
            )
            return [
                QuestionAnswer(
                    short_answer=row["short_answer"],
                    full_answer=row["full_answer"],
                )
                for row in cursor.fetchall()
            ]

    def get_rule(self, question_id: int) -> dict | None:
        """Get grammar rule for a question.

        Args:
            question_id: Question database ID.

        Returns:
            Dict with section_letter and rule, or None if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT section_letter, rule
                FROM questions
                WHERE id = ?
                """,
                (question_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_topic_for_question(self, question_id: int) -> str | None:
        """Get topic name for a specific question via exercise and unit.

        Args:
            question_id: Question database ID.

        Returns:
            Topic name or None if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT t.name
                FROM questions q
                JOIN exercises e ON q.exercise_id = e.id
                JOIN units u ON e.unit_id = u.id
                JOIN unit_topics ut ON u.id = ut.unit_id
                JOIN topics t ON ut.topic_id = t.id
                WHERE q.id = ?
                """,
                (question_id,),
            )
            row = cursor.fetchone()
            return row["name"] if row else None

    def get_user_auth_status(self, telegram_id: int) -> str | None:
        """Get authorization status for a user.

        Args:
            telegram_id: Telegram user ID.

        Returns:
            Status string ('pending', 'approved', 'rejected') or None if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT status FROM authorized_users WHERE telegram_id = ?",
                (telegram_id,),
            )
            row = cursor.fetchone()
            return row["status"] if row else None

    def add_user(
        self,
        telegram_id: int,
        full_name: str,
        telegram_username: str | None,
    ) -> None:
        """Add a new user as pending authorization.

        Args:
            telegram_id: Telegram user ID.
            full_name: User's full name.
            telegram_username: User's Telegram username (optional).
        """
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO authorized_users (telegram_id, full_name, telegram_username)
                VALUES (?, ?, ?)
                """,
                (telegram_id, full_name, telegram_username),
            )

    def set_user_status(
        self,
        telegram_id: int,
        status: str,
        handled_by: int,
    ) -> None:
        """Set authorization status for a user.

        Args:
            telegram_id: Telegram user ID.
            status: New status ('approved' or 'rejected').
            handled_by: Admin Telegram ID who performed the action.
        """
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE authorized_users
                SET status = ?, handled_at = CURRENT_TIMESTAMP, handled_by = ?
                WHERE telegram_id = ?
                """,
                (status, handled_by, telegram_id),
            )

    def reset_user_to_pending(
        self,
        telegram_id: int,
        full_name: str,
        telegram_username: str | None,
    ) -> None:
        """Reset a rejected user back to pending status.

        Args:
            telegram_id: Telegram user ID.
            full_name: User's full name.
            telegram_username: User's Telegram username (optional).
        """
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE authorized_users
                SET status = 'pending', full_name = ?, telegram_username = ?,
                    handled_at = NULL, handled_by = NULL
                WHERE telegram_id = ?
                """,
                (full_name, telegram_username, telegram_id),
            )

    def get_pending_users(self) -> list[dict]:
        """Get all users with pending authorization status.

        Returns:
            List of pending user dicts with telegram_id, full_name, telegram_username, created_at.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT telegram_id, full_name, telegram_username, created_at
                FROM authorized_users
                WHERE status = 'pending'
                ORDER BY created_at ASC
                """
            )
            return [dict(row) for row in cursor.fetchall()]
