"""Bot states for user session management."""

from dataclasses import dataclass, field


@dataclass
class UserSession:
    """User session state."""

    user_id: int
    current_exercise_id: int | None = None
    current_question_id: str | None = None
    current_question_db_id: int | None = None
    current_topic_id: int | None = None
    current_topic_name: str | None = None
    current_unit_number: int | None = None
    current_is_open_ended: bool = False
    unit_shown: bool = False
    answered: bool = False
    available_questions: list[str] = field(default_factory=list)
    show_rule: bool = True

    def clear_exercise(self) -> None:
        """Clear current exercise context."""
        self.current_exercise_id = None
        self.current_question_id = None
        self.current_question_db_id = None
        self.current_topic_name = None
        self.current_unit_number = None
        self.current_is_open_ended = False
        self.unit_shown = False
        self.answered = False
        self.available_questions = []


class StateManager:
    """Manager for user sessions."""

    def __init__(self) -> None:
        """Initialize state manager."""
        self.sessions: dict[int, UserSession] = {}

    def get_session(self, user_id: int) -> UserSession:
        """Get or create user session.

        Args:
            user_id: Telegram user ID.

        Returns:
            User session.
        """
        if user_id not in self.sessions:
            self.sessions[user_id] = UserSession(user_id=user_id)
        return self.sessions[user_id]

    def clear_session(self, user_id: int) -> None:
        """Clear user session.

        Args:
            user_id: Telegram user ID.
        """
        if user_id in self.sessions:
            del self.sessions[user_id]

    def set_exercise(
        self,
        user_id: int,
        exercise_id: int,
        question_id: str,
        question_db_id: int,
        topic_id: int | None,
        topic_name: str,
        unit_number: int,
        available_questions: list[str],
        is_open_ended: bool = False,
    ) -> None:
        """Set current exercise for user.

        Args:
            user_id: Telegram user ID.
            exercise_id: Exercise database ID.
            question_id: Current question number.
            question_db_id: Question database ID.
            topic_id: Current topic ID (None for random).
            topic_name: Current topic name.
            unit_number: Current unit number.
            available_questions: List of available question numbers.
            is_open_ended: Whether the question is open-ended.
        """
        session = self.get_session(user_id)
        session.current_exercise_id = exercise_id
        session.current_question_id = question_id
        session.current_question_db_id = question_db_id
        session.current_topic_id = topic_id
        session.current_topic_name = topic_name
        session.current_unit_number = unit_number
        session.current_is_open_ended = is_open_ended
        session.unit_shown = False
        session.answered = False
        session.available_questions = available_questions

    def mark_unit_shown(self, user_id: int) -> None:
        """Mark unit as shown for user.

        Args:
            user_id: Telegram user ID.
        """
        session = self.get_session(user_id)
        session.unit_shown = True

    def mark_answered(self, user_id: int) -> None:
        """Mark question as answered for user.

        Args:
            user_id: Telegram user ID.
        """
        session = self.get_session(user_id)
        session.answered = True

    def toggle_show_rule(self, user_id: int) -> bool:
        """Toggle show_rule setting for user.

        Args:
            user_id: Telegram user ID.

        Returns:
            New show_rule value.
        """
        session = self.get_session(user_id)
        session.show_rule = not session.show_rule
        return session.show_rule


state_manager = StateManager()
