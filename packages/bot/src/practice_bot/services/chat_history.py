"""In-memory assistant transcripts, scoped to a user's current exercise."""

from practice_bot.models.agents import ChatMessage, ChatRole

DEFAULT_MAX_MESSAGES = 20


class ChatHistoryManager:
    """Keeps the recent assistant conversation for each user and exercise.

    A user only ever converses about the exercise in front of them, so
    :meth:`start_exercise` drops every other exercise's transcript, and each
    transcript is capped at ``max_messages``. Without both, a long-running
    process would accumulate one list per exercise per user forever.
    """

    def __init__(self, max_messages: int = DEFAULT_MAX_MESSAGES) -> None:
        """Initialize empty history storage.

        Args:
            max_messages: Newest messages kept per exercise. Must be positive.
        """
        self._max_messages = max(1, max_messages)
        self._history: dict[int, dict[int, list[ChatMessage]]] = {}

    def add_turn(
        self,
        user_id: int,
        exercise_id: int,
        role: ChatRole,
        content: str,
    ) -> None:
        """Append one message, discarding the oldest beyond the cap.

        Args:
            user_id: The user's Telegram ID.
            exercise_id: The exercise being discussed.
            role: Who produced the message.
            content: Message text.
        """
        transcript = self._history.setdefault(user_id, {}).setdefault(exercise_id, [])
        transcript.append(ChatMessage(role=role, content=content))
        if len(transcript) > self._max_messages:
            del transcript[: -self._max_messages]

    def history(self, user_id: int, exercise_id: int) -> list[ChatMessage]:
        """Return the transcript for one user and exercise.

        Args:
            user_id: The user's Telegram ID.
            exercise_id: The exercise being discussed.

        Returns:
            The messages in order, oldest first; empty when there are none.
        """
        return list(self._history.get(user_id, {}).get(exercise_id, ()))

    def start_exercise(self, user_id: int, exercise_id: int) -> None:
        """Keep only the given exercise's transcript for this user.

        Args:
            user_id: The user's Telegram ID.
            exercise_id: The exercise the user just started.
        """
        transcripts = self._history.get(user_id)
        if transcripts is None:
            return
        kept = transcripts.get(exercise_id)
        if kept is None:
            # Nothing to keep, so drop the user's entry rather than leaving an
            # empty mapping behind for every user who ever asked a question.
            del self._history[user_id]
            return
        self._history[user_id] = {exercise_id: kept}

    def forget_user(self, user_id: int) -> None:
        """Drop everything stored for one user.

        Args:
            user_id: The user's Telegram ID.
        """
        self._history.pop(user_id, None)
