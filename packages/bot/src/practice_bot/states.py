"""In-memory session state, one entry per user."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from practice_core.models import Exercise, Question

DEFAULT_IDLE_TTL = timedelta(hours=12)


def _now() -> datetime:
    """Return the current UTC time."""
    return datetime.now(UTC)


@dataclass(slots=True)
class ActiveExercise:
    """The exercise and question a user is working on right now.

    Grouping them makes the states that used to be spellable — a question
    without its exercise, an exercise without its unit — impossible.

    The image travels with them: it is a few hundred kilobytes that cannot
    change while the exercise is in front of the user, and every agent call
    needs it, so it is read once here rather than per message.
    """

    exercise: Exercise
    question: Question
    topic_id: int | None
    topic_name: str
    image: bytes | None = None
    answered: bool = False


@dataclass(slots=True)
class UserSession:
    """What the bot remembers about one user between updates."""

    user_id: int
    active: ActiveExercise | None = None
    # Kept when the exercise is cleared, so "Same Topic" survives a new draw.
    last_topic_id: int | None = None
    show_rule: bool = True
    last_seen: datetime = field(default_factory=_now)

    @property
    def has_previous_topic(self) -> bool:
        """Whether the user has already practised a specific topic."""
        return self.last_topic_id is not None


class SessionStore:
    """Holds user sessions for the lifetime of the process.

    Sessions are deliberately not persisted: they are a convenience (which
    exercise am I on, do I want rules shown), and a restart costing the user one
    ``/start`` is cheaper than the schema and migrations to keep them. Idle
    sessions are evicted so that a long-running bot does not grow one entry per
    person who ever messaged it.
    """

    def __init__(
        self,
        idle_ttl: timedelta = DEFAULT_IDLE_TTL,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        """Initialize the store.

        Args:
            idle_ttl: How long a session survives without activity.
            clock: Time source, injectable for tests.
        """
        self._idle_ttl = idle_ttl
        self._clock = clock
        self._sessions: dict[int, UserSession] = {}

    def __len__(self) -> int:
        """Return the number of live sessions."""
        return len(self._sessions)

    def get(self, user_id: int) -> UserSession:
        """Return a user's session, creating it if needed.

        Any interaction is also the moment to drop sessions nobody has touched
        in a while, which keeps eviction free of background tasks.

        Args:
            user_id: Telegram user ID.

        Returns:
            The user's session, marked as just used.
        """
        now = self._clock()
        self._evict_idle(now)

        session = self._sessions.get(user_id)
        if session is None:
            session = UserSession(user_id=user_id, last_seen=now)
            self._sessions[user_id] = session
        else:
            session.last_seen = now
        return session

    def forget(self, user_id: int) -> None:
        """Drop a user's session.

        Args:
            user_id: Telegram user ID.
        """
        self._sessions.pop(user_id, None)

    def start_exercise(self, user_id: int, active: ActiveExercise) -> UserSession:
        """Make an exercise the user's current one.

        Args:
            user_id: Telegram user ID.
            active: The exercise and question just sent.

        Returns:
            The updated session.
        """
        session = self.get(user_id)
        session.active = active
        if active.topic_id is not None:
            session.last_topic_id = active.topic_id
        return session

    def toggle_show_rule(self, user_id: int) -> bool:
        """Flip whether grammar rules are shown after an answer.

        Args:
            user_id: Telegram user ID.

        Returns:
            The new setting.
        """
        session = self.get(user_id)
        session.show_rule = not session.show_rule
        return session.show_rule

    def _evict_idle(self, now: datetime) -> None:
        """Drop sessions untouched for longer than the TTL.

        Args:
            now: Current time.
        """
        cutoff = now - self._idle_ttl
        stale = [
            user_id
            for user_id, session in self._sessions.items()
            if session.last_seen < cutoff
        ]
        for user_id in stale:
            del self._sessions[user_id]
