"""Tests for the in-memory session store."""

from datetime import UTC, datetime, timedelta

from english_practice.bot.states import ActiveExercise, SessionStore, UserSession
from english_practice.models.book import Exercise, Question


class _Clock:
    """A hand-wound clock, so TTL behaviour is testable without sleeping."""

    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


def _active(
    exercise: Exercise, question: Question, topic_id: int | None
) -> ActiveExercise:
    """Build an active exercise for the given topic."""
    return ActiveExercise(
        exercise=exercise,
        question=question,
        topic_id=topic_id,
        topic_name="Present Tenses",
    )


class TestSessions:
    """Tests for creating and reusing sessions."""

    def test_get_creates_once_and_reuses(self, sessions: SessionStore) -> None:
        first = sessions.get(1)
        assert sessions.get(1) is first
        assert len(sessions) == 1

    def test_new_session_defaults(self, sessions: SessionStore) -> None:
        session = sessions.get(1)

        assert session.active is None
        assert session.show_rule is True
        assert session.has_previous_topic is False

    def test_forget_drops_the_session(self, sessions: SessionStore) -> None:
        sessions.get(1)
        sessions.forget(1)

        assert len(sessions) == 0

    def test_forget_is_idempotent(self, sessions: SessionStore) -> None:
        sessions.forget(404)

        assert len(sessions) == 0


class TestActiveExercise:
    """Tests for tracking the exercise in progress."""

    def test_start_exercise_records_it(
        self, sessions: SessionStore, exercise: Exercise, question: Question
    ) -> None:
        session = sessions.start_exercise(1, _active(exercise, question, 3))

        assert session.active is not None
        assert session.active.exercise.id == exercise.id
        assert session.active.question.question_id == "1"
        assert session.active.answered is False

    def test_specific_topic_is_remembered(
        self, sessions: SessionStore, exercise: Exercise, question: Question
    ) -> None:
        sessions.start_exercise(1, _active(exercise, question, 3))

        assert sessions.get(1).last_topic_id == 3
        assert sessions.get(1).has_previous_topic is True

    def test_random_draw_does_not_clear_the_remembered_topic(
        self, sessions: SessionStore, exercise: Exercise, question: Question
    ) -> None:
        """A random exercise must not take away the "Same Topic" option."""
        sessions.start_exercise(1, _active(exercise, question, 3))
        sessions.start_exercise(1, _active(exercise, question, None))

        assert sessions.get(1).last_topic_id == 3

    def test_starting_a_new_exercise_resets_answered(
        self, sessions: SessionStore, exercise: Exercise, question: Question
    ) -> None:
        session = sessions.start_exercise(1, _active(exercise, question, 3))
        assert session.active is not None
        session.active.answered = True

        session = sessions.start_exercise(1, _active(exercise, question, 3))

        assert session.active is not None
        assert session.active.answered is False


class TestShowRule:
    """Tests for the rule-display toggle."""

    def test_toggles_off_then_on(self, sessions: SessionStore) -> None:
        assert sessions.toggle_show_rule(1) is False
        assert sessions.toggle_show_rule(1) is True

    def test_toggle_is_per_user(self, sessions: SessionStore) -> None:
        sessions.toggle_show_rule(1)

        assert sessions.get(2).show_rule is True


class TestEviction:
    """A long-running bot must not keep a session per person forever."""

    def test_idle_session_is_evicted(self) -> None:
        clock = _Clock()
        sessions = SessionStore(idle_ttl=timedelta(minutes=30), clock=clock)
        sessions.get(1)

        clock.advance(timedelta(minutes=31))
        sessions.get(2)

        assert len(sessions) == 1

    def test_activity_keeps_a_session_alive(self) -> None:
        clock = _Clock()
        sessions = SessionStore(idle_ttl=timedelta(minutes=30), clock=clock)
        sessions.get(1)

        for _ in range(4):
            clock.advance(timedelta(minutes=20))
            sessions.get(1)

        assert len(sessions) == 1

    def test_last_seen_is_updated_on_access(self) -> None:
        clock = _Clock()
        sessions = SessionStore(clock=clock)
        session: UserSession = sessions.get(1)
        created_at = session.last_seen

        clock.advance(timedelta(minutes=5))
        sessions.get(1)

        assert session.last_seen > created_at
