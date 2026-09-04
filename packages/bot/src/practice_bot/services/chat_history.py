"""In-memory assistant transcripts, scoped to a user's current exercise."""

from practice_bot.models.agents import ChatMessage, ChatRole

DEFAULT_MAX_MESSAGES = 20


class ChatHistoryManager:
    """Keeps the recent assistant conversation for each user and exercise."""

    def __init__(self, max_messages: int = DEFAULT_MAX_MESSAGES) -> None:
        """Initialize empty history storage."""
        self._max_messages = max(1, max_messages)
        self._history: dict[int, dict[int, list[ChatMessage]]] = {}

    def add_turn(
        self,
        user_id: int,
        exercise_id: int,
        role: ChatRole,
        content: str,
    ) -> None:
        """Append one message, discarding the oldest beyond the cap."""
        transcript = self._history.setdefault(user_id, {}).setdefault(exercise_id, [])
        transcript.append(ChatMessage(role=role, content=content))
        if len(transcript) > self._max_messages:
            del transcript[: -self._max_messages]

    def history(self, user_id: int, exercise_id: int) -> list[ChatMessage]:
        """Return the transcript for one user and exercise."""
        return list(self._history.get(user_id, {}).get(exercise_id, ()))

    def start_exercise(self, user_id: int, exercise_id: int) -> None:
        """Keep only the given exercise's transcript for this user."""
        transcripts = self._history.get(user_id)
        if transcripts is None:
            return
        kept = transcripts.get(exercise_id)
        if kept is None:
            # Drop the entry rather than leave an empty mapping behind for ever.
            del self._history[user_id]
            return
        self._history[user_id] = {exercise_id: kept}

    def forget_user(self, user_id: int) -> None:
        """Drop everything stored for one user."""
        self._history.pop(user_id, None)
