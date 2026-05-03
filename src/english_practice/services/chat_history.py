"""Chat history manager for assistant agent."""

from typing import Any


class ChatHistoryManager:
    """Manages chat history per user and exercise.

    Structure: {user_id: {exercise_id: [messages]}}
    History is cleared when a new exercise is processed.
    """

    def __init__(self) -> None:
        """Initialize empty chat history storage."""
        self._history: dict[int, dict[int, list[dict[str, Any]]]] = {}

    def add_message(
        self,
        user_id: int,
        exercise_id: int | None,
        role: str,
        content: str,
    ) -> None:
        """Add a message to the chat history.

        Args:
            user_id: The user's ID.
            exercise_id: The exercise database ID.
            role: Message role ('user' or 'assistant').
            content: Message content.
        """
        if user_id not in self._history:
            self._history[user_id] = {}

        if exercise_id not in self._history[user_id]:
            self._history[user_id][exercise_id] = []

        self._history[user_id][exercise_id].append(
            {
                "role": role,
                "content": content,
            }
        )

    def get_history(
        self,
        user_id: int,
        exercise_id: int | None,
    ) -> list[dict[str, Any]]:
        """Get chat history for a specific user and exercise.

        Args:
            user_id: The user's ID.
            exercise_id: The exercise database ID.

        Returns:
            List of message dictionaries with 'role' and 'content' keys.
        """
        if user_id not in self._history:
            return []

        return self._history[user_id].get(exercise_id, [])

    def clear_history(self, user_id: int, exercise_id: int | None) -> None:
        """Clear chat history for a specific user and exercise.

        Args:
            user_id: The user's ID.
            exercise_id: The exercise database ID.
        """
        if user_id in self._history and exercise_id in self._history[user_id]:
            del self._history[user_id][exercise_id]

    def clear_user_history(self, user_id: int) -> None:
        """Clear all chat history for a user.

        Args:
            user_id: The user's ID.
        """
        if user_id in self._history:
            del self._history[user_id]

    def on_new_image(self, user_id: int, exercise_id: int | None) -> None:
        """Handle new exercise - clear history for all other exercises of this user.

        Args:
            user_id: The user's ID.
            exercise_id: The new exercise database ID.
        """
        if user_id in self._history:
            # Keep only the new exercise's history (if any)
            new_history: dict[int | None, list[dict[str, Any]]] = {}
            if exercise_id in self._history[user_id]:
                new_history[exercise_id] = self._history[user_id][exercise_id]
            self._history[user_id] = new_history
