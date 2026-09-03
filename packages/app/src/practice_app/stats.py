"""Practice progress, kept in a small SQLite file in the app's storage.

One row per graded answer is the whole model. Everything the stats screen shows
— accuracy, streaks, the last week, the per-topic table — is derived from those
rows on read, so there is no aggregate to keep in step and no migration to run
when a new figure is added to the screen.
"""

import asyncio
import sqlite3
from collections.abc import Callable, Iterator, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

__all__ = [
    "Attempt",
    "DayStat",
    "StatsStore",
    "StatsSummary",
    "TopicStat",
]

RECENT_DAYS = 7

_SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY,
    answered_at TEXT NOT NULL,
    topic_name TEXT NOT NULL,
    unit_number INTEGER NOT NULL,
    exercise_id TEXT NOT NULL,
    question_id TEXT NOT NULL,
    is_correct INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attempts_answered_at ON attempts(answered_at);
"""


def _now() -> datetime:
    """Return the current time, in UTC."""
    return datetime.now(UTC)


def _local_date(stamp: str) -> date | None:
    """Return the local calendar day a stored timestamp falls on.

    Args:
        stamp: An ISO-8601 timestamp as written by :meth:`StatsStore.record`.

    Returns:
        The local date, or ``None`` when the value cannot be parsed — a row
        that predates a format change must not take the whole screen down.
    """
    try:
        parsed = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone().date()


@dataclass(frozen=True, slots=True)
class Attempt:
    """One graded answer, as it is recorded."""

    topic_name: str
    unit_number: int
    exercise_id: str
    question_id: str
    is_correct: bool


@dataclass(frozen=True, slots=True)
class TopicStat:
    """How a user is doing on one topic."""

    name: str
    attempts: int
    correct: int

    @property
    def accuracy(self) -> float:
        """Return the share of correct answers, from 0 to 1."""
        return self.correct / self.attempts if self.attempts else 0.0


@dataclass(frozen=True, slots=True)
class DayStat:
    """How a user did on one calendar day."""

    day: date
    attempts: int
    correct: int

    @property
    def accuracy(self) -> float:
        """Return the share of correct answers, from 0 to 1."""
        return self.correct / self.attempts if self.attempts else 0.0


@dataclass(frozen=True, slots=True)
class StatsSummary:
    """Everything the stats screen shows, computed in one pass."""

    total: int = 0
    correct: int = 0
    current_streak: int = 0
    best_streak: int = 0
    days_practised: int = 0
    day_streak: int = 0
    recent_days: tuple[DayStat, ...] = ()
    topics: tuple[TopicStat, ...] = ()
    first_day: date | None = None
    last_day: date | None = None

    @property
    def accuracy(self) -> float:
        """Return the share of correct answers, from 0 to 1."""
        return self.correct / self.total if self.total else 0.0

    @property
    def wrong(self) -> int:
        """Return how many answers were marked wrong."""
        return self.total - self.correct

    @property
    def today(self) -> DayStat:
        """Return today's figures, which are the last of the recent days."""
        if self.recent_days:
            return self.recent_days[-1]
        return DayStat(day=date.today(), attempts=0, correct=0)

    @property
    def is_empty(self) -> bool:
        """Whether nothing has been graded yet."""
        return self.total == 0


@dataclass(slots=True)
class _Tally:
    """Attempts and hits while they are still being counted.

    The loop below used to carry these as a two-slot list, so "attempts" and
    "correct" were positions rather than names -- restated at six sites, and a
    transposition anywhere reported an accuracy above 100% with nothing
    failing. :class:`TopicStat` and :class:`DayStat` are the frozen forms of
    the same pair, built from this once the counting is done.
    """

    attempts: int = 0
    correct: int = 0

    def add(self, hit: bool) -> None:
        """Count one attempt, correct or not."""
        self.attempts += 1
        self.correct += hit


def _summarize(
    rows: Sequence[tuple[str, str, int]], today: date, days: int
) -> StatsSummary:
    """Build the summary from every recorded attempt, oldest first.

    Args:
        rows: ``(answered_at, topic_name, is_correct)`` in insertion order.
        today: The local date to anchor "today" and the streaks to.
        days: How many recent days the chart covers.

    Returns:
        The summary.
    """
    # The chart needs at least one column whatever the caller asked for.
    days = max(1, days)

    if not rows:
        return StatsSummary(
            recent_days=tuple(
                DayStat(day=today - timedelta(days=offset), attempts=0, correct=0)
                for offset in reversed(range(days))
            )
        )

    correct = 0
    streak = 0
    best_streak = 0
    per_day: dict[date, _Tally] = {}
    per_topic: dict[str, _Tally] = {}

    for stamp, topic_name, is_correct in rows:
        hit = bool(is_correct)
        correct += hit
        streak = streak + 1 if hit else 0
        best_streak = max(best_streak, streak)

        per_topic.setdefault(topic_name or "Unknown", _Tally()).add(hit)

        day = _local_date(stamp)
        if day is not None:
            per_day.setdefault(day, _Tally()).add(hit)

    practised = sorted(per_day)
    day_streak = 0
    if practised:
        # A day that is not over yet has not broken anything, so a streak that
        # ended yesterday still counts until midnight.
        cursor = today if today in per_day else today - timedelta(days=1)
        while cursor in per_day:
            day_streak += 1
            cursor -= timedelta(days=1)

    blank = _Tally()
    recent = tuple(
        DayStat(
            day=day,
            attempts=per_day.get(day, blank).attempts,
            correct=per_day.get(day, blank).correct,
        )
        for day in (today - timedelta(days=offset) for offset in reversed(range(days)))
    )

    topics = tuple(
        sorted(
            (
                TopicStat(name=name, attempts=tally.attempts, correct=tally.correct)
                for name, tally in per_topic.items()
            ),
            key=lambda stat: (-stat.attempts, stat.name),
        )
    )

    return StatsSummary(
        total=len(rows),
        correct=correct,
        current_streak=streak,
        best_streak=best_streak,
        days_practised=len(per_day),
        day_streak=day_streak,
        recent_days=recent,
        topics=topics,
        first_day=practised[0] if practised else None,
        last_day=practised[-1] if practised else None,
    )


class StatsStore:
    """Records graded answers and reports on them."""

    def __init__(self, db_path: Path, clock: Callable[[], datetime] = _now) -> None:
        """Initialize the store.

        Args:
            db_path: The SQLite file to use. Created, with its directory, on
                first write.
            clock: Time source, injectable for tests.
        """
        self.db_path = db_path
        self._clock = clock

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection with the schema applied, and always close it.

        Yields:
            A connection that commits on success and rolls back on error.
        """
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path, timeout=5.0)) as conn:
            conn.row_factory = sqlite3.Row
            conn.executescript(_SCHEMA)
            with conn:
                yield conn

    def _record_sync(self, attempt: Attempt, answered_at: str) -> None:
        """Insert one attempt."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO attempts (
                    answered_at, topic_name, unit_number, exercise_id,
                    question_id, is_correct
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    answered_at,
                    attempt.topic_name,
                    attempt.unit_number,
                    attempt.exercise_id,
                    attempt.question_id,
                    int(attempt.is_correct),
                ),
            )

    def _rows_sync(self) -> list[tuple[str, str, int]]:
        """Return every attempt, oldest first."""
        with self._connect() as conn:
            return [
                (row["answered_at"], row["topic_name"], row["is_correct"])
                for row in conn.execute(
                    "SELECT answered_at, topic_name, is_correct "
                    "FROM attempts ORDER BY id"
                )
            ]

    def _reset_sync(self) -> None:
        """Delete every attempt."""
        with self._connect() as conn:
            conn.execute("DELETE FROM attempts")

    async def record(self, attempt: Attempt) -> None:
        """Record one graded answer.

        Args:
            attempt: What was answered, and whether it was right.
        """
        await asyncio.to_thread(
            self._record_sync, attempt, self._clock().isoformat(timespec="seconds")
        )

    async def summary(self, days: int = RECENT_DAYS) -> StatsSummary:
        """Return the figures the stats screen shows.

        Args:
            days: How many recent days the day-by-day chart covers.

        Returns:
            The summary; empty but well-formed when nothing is recorded yet.
        """
        rows = await asyncio.to_thread(self._rows_sync)
        today = self._clock().astimezone().date()
        return _summarize(rows, today, days)

    async def reset(self) -> None:
        """Delete every recorded attempt."""
        await asyncio.to_thread(self._reset_sync)
