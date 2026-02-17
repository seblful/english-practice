"""Chat history manager for assistant agent."""

from pathlib import Path
from typing import Any


class ChatHistoryManager:
    """Manages chat history per user and image.

    Structure: {user_id: {image_path: [messages]}}
    History is cleared when a new image is processed.
    """

    def __init__(self) -> None:
        """Initialize empty chat history storage."""
        self._history: dict[int, dict[str, list[dict[str, Any]]]] = {}

    def add_message(
        self,
        user_id: int,
        image_path: Path,
        role: str,
        content: str,
    ) -> None:
        """Add a message to the chat history.

        Args:
            user_id: The user's ID.
            image_path: Path to the current exercise image.
            role: Message role ('user' or 'assistant').
            content: Message content.
        """
        image_key = str(image_path)

        if user_id not in self._history:
            self._history[user_id] = {}

        if image_key not in self._history[user_id]:
            self._history[user_id][image_key] = []

        self._history[user_id][image_key].append(
            {
                "role": role,
                "content": content,
            }
        )

    def get_history(
        self,
        user_id: int,
        image_path: Path,
    ) -> list[dict[str, Any]]:
        """Get chat history for a specific user and image.

        Args:
            user_id: The user's ID.
            image_path: Path to the current exercise image.

        Returns:
            List of message dictionaries with 'role' and 'content' keys.
        """
        image_key = str(image_path)

        if user_id not in self._history:
            return []

        return self._history[user_id].get(image_key, [])

    def clear_history(self, user_id: int, image_path: Path) -> None:
        """Clear chat history for a specific user and image.

        Args:
            user_id: The user's ID.
            image_path: Path to the current exercise image.
        """
        image_key = str(image_path)

        if user_id in self._history and image_key in self._history[user_id]:
            del self._history[user_id][image_key]

    def clear_user_history(self, user_id: int) -> None:
        """Clear all chat history for a user.

        Args:
            user_id: The user's ID.
        """
        if user_id in self._history:
            del self._history[user_id]

    def on_new_image(self, user_id: int, new_image_path: Path) -> None:
        """Handle new image - clear history for all other images of this user.

        Args:
            user_id: The user's ID.
            new_image_path: Path to the new exercise image.
        """
        new_image_key = str(new_image_path)

        if user_id in self._history:
            # Keep only the new image's history (if any)
            new_history = {}
            if new_image_key in self._history[user_id]:
                new_history[new_image_key] = self._history[user_id][new_image_key]
            self._history[user_id] = new_history
