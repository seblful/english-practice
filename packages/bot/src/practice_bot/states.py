"""In-memory session state, one entry per user."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from practice_core.lesson import ActiveExercise

DEFAULT_IDLE_TTL = timedelta(hours=12)


def _now() -> datetime:
    """Return the current UTC time."""
    return datetime.now(UTC)


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
    """Holds user sessions for the lifetime of the process."""

    def __init__(
        self,
        idle_ttl: timedelta = DEFAULT_IDLE_TTL,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        """Initialize the store."""
        self._idle_ttl = idle_ttl
        self._clock = clock
        self._sessions: dict[int, UserSession] = {}

    def __len__(self) -> int:
        """Return the number of live sessions."""
        return len(self._sessions)

    def get(self, user_id: int) -> UserSession:
        """Return a user's session, creating it if needed."""
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
        """Drop a user's session."""
        self._sessions.pop(user_id, None)

    def start_exercise(self, user_id: int, active: ActiveExercise) -> UserSession:
        """Make an exercise the user's current one."""
        session = self.get(user_id)
        session.active = active
        if active.topic_id is not None:
            session.last_topic_id = active.topic_id
        return session

    def toggle_show_rule(self, user_id: int) -> bool:
        """Flip whether grammar rules are shown after an answer."""
        session = self.get(user_id)
        session.show_rule = not session.show_rule
        return session.show_rule

    def _evict_idle(self, now: datetime) -> None:
        """Drop sessions untouched for longer than the TTL."""
        cutoff = now - self._idle_ttl
        stale = [
            user_id
            for user_id, session in self._sessions.items()
            if session.last_seen < cutoff
        ]
        for user_id in stale:
            del self._sessions[user_id]
