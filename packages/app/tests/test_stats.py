"""Tests for the progress store and the figures it derives."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from practice_app.stats import Attempt, StatsStore, _summarize


def _attempt(*, correct: bool, topic: str = "Present Tenses") -> Attempt:
    """Return one recorded answer."""
    return Attempt(
        topic_name=topic,
        unit_number=1,
        exercise_id="1.1",
        question_id="2",
        is_correct=correct,
    )


@pytest.fixture
def store(tmp_path: Path, frozen_clock: Callable[[], datetime]) -> StatsStore:
    """A store whose clock is stuck, so the streaks are deterministic."""
    return StatsStore(tmp_path / "progress.db", clock=frozen_clock)


class TestEmptyStore:
    async def test_reports_nothing_yet(self, store: StatsStore) -> None:
        summary = await store.summary()

        assert summary.is_empty is True
        assert summary.total == 0
        assert summary.accuracy == 0.0

    async def test_still_shows_a_full_week(self, store: StatsStore) -> None:
        """The chart must have seven columns before the first answer."""
        summary = await store.summary()

        assert len(summary.recent_days) == 7
        assert all(day.attempts == 0 for day in summary.recent_days)

    async def test_today_is_well_formed(self, store: StatsStore) -> None:
        today = (await store.summary()).today

        assert today.attempts == 0
        assert today.correct == 0

    async def test_the_database_is_created_on_first_write(
        self, store: StatsStore
    ) -> None:
        assert not store.db_path.exists()

        await store.record(_attempt(correct=True))

        assert store.db_path.is_file()


class TestTotals:
    async def test_counts_and_accuracy(self, store: StatsStore) -> None:
        for correct in (True, True, False, True):
            await store.record(_attempt(correct=correct))

        summary = await store.summary()

        assert summary.total == 4
        assert summary.correct == 3
        assert summary.wrong == 1
        assert summary.accuracy == pytest.approx(0.75)

    async def test_topics_are_ranked_by_volume(self, store: StatsStore) -> None:
        for _ in range(3):
            await store.record(_attempt(correct=True, topic="Past Tenses"))
        await store.record(_attempt(correct=False, topic="Articles"))

        topics = (await store.summary()).topics

        assert [topic.name for topic in topics] == ["Past Tenses", "Articles"]
        assert topics[0].accuracy == 1.0
        assert topics[1].accuracy == 0.0

    async def test_an_answer_with_no_topic_is_still_counted(
        self, store: StatsStore
    ) -> None:
        await store.record(_attempt(correct=True, topic=""))

        assert (await store.summary()).topics[0].name == "Unknown"


class TestStreaks:
    async def test_the_current_streak_counts_back_from_the_last_answer(
        self, store: StatsStore
    ) -> None:
        for correct in (True, True, False, True, True, True):
            await store.record(_attempt(correct=correct))

        summary = await store.summary()

        assert summary.current_streak == 3
        assert summary.best_streak == 3

    async def test_a_wrong_answer_ends_the_streak(self, store: StatsStore) -> None:
        for correct in (True, True, True, False):
            await store.record(_attempt(correct=correct))

        summary = await store.summary()

        assert summary.current_streak == 0
        assert summary.best_streak == 3


class TestReset:
    async def test_forgets_everything(self, store: StatsStore) -> None:
        await store.record(_attempt(correct=True))

        await store.reset()

        assert (await store.summary()).is_empty is True

    async def test_resetting_an_untouched_store_is_harmless(
        self, store: StatsStore
    ) -> None:
        await store.reset()

        assert (await store.summary()).total == 0


class TestSummarize:
    """The arithmetic, over rows a test can place on exact days."""

    def _rows(self, *offsets: int) -> list[tuple[str, str, int]]:
        """Return one correct answer per day offset, oldest first."""
        base = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
        return [
            ((base - timedelta(days=offset)).isoformat(), "Topic", 1)
            for offset in sorted(offsets, reverse=True)
        ]

    def test_the_day_streak_counts_consecutive_days(self) -> None:
        summary = _summarize(self._rows(0, 1, 2), datetime(2026, 3, 14).date(), 7)

        assert summary.day_streak == 3
        assert summary.days_practised == 3

    def test_a_gap_ends_the_day_streak(self) -> None:
        summary = _summarize(self._rows(0, 1, 3), datetime(2026, 3, 14).date(), 7)

        assert summary.day_streak == 2

    def test_a_streak_that_ended_yesterday_survives_until_midnight(self) -> None:
        """The day is not over, so nothing has been broken yet."""
        summary = _summarize(self._rows(1, 2), datetime(2026, 3, 14).date(), 7)

        assert summary.day_streak == 2

    def test_a_streak_that_ended_before_yesterday_is_over(self) -> None:
        summary = _summarize(self._rows(2, 3), datetime(2026, 3, 14).date(), 7)

        assert summary.day_streak == 0

    def test_the_window_covers_the_requested_days_in_order(self) -> None:
        summary = _summarize(self._rows(0), datetime(2026, 3, 14).date(), 3)

        assert len(summary.recent_days) == 3
        assert [day.day.day for day in summary.recent_days] == [12, 13, 14]

    def test_answers_older_than_the_window_still_count_in_the_totals(self) -> None:
        summary = _summarize(self._rows(0, 30), datetime(2026, 3, 14).date(), 7)

        assert summary.total == 2
        assert sum(day.attempts for day in summary.recent_days) == 1

    def test_the_first_and_last_day_bracket_the_history(self) -> None:
        summary = _summarize(self._rows(0, 5), datetime(2026, 3, 14).date(), 7)

        assert summary.first_day == datetime(2026, 3, 9).date()
        assert summary.last_day == datetime(2026, 3, 14).date()

    def test_an_unparsable_timestamp_does_not_take_the_screen_down(self) -> None:
        """A row from a format change must cost its day, not the whole page."""
        rows = [("not a date", "Topic", 1), *self._rows(0)]

        summary = _summarize(rows, datetime(2026, 3, 14).date(), 7)

        assert summary.total == 2
        assert summary.days_practised == 1

    def test_a_naive_timestamp_is_read_as_utc(self) -> None:
        rows = [("2026-03-14T12:00:00", "Topic", 1)]

        summary = _summarize(rows, datetime(2026, 3, 14).date(), 7)

        assert summary.days_practised == 1

    def test_a_window_of_at_least_one_day(self) -> None:
        summary = _summarize(self._rows(0), datetime(2026, 3, 14).date(), 0)

        assert len(summary.recent_days) == 1


class TestDayAndTopicStats:
    def test_a_day_with_no_answers_has_no_accuracy(self) -> None:
        summary = _summarize([], datetime(2026, 3, 14).date(), 7)

        assert summary.recent_days[0].accuracy == 0.0

    def test_a_topic_accuracy(self) -> None:
        rows = [
            ("2026-03-14T12:00:00+00:00", "Topic", 1),
            ("2026-03-14T12:01:00+00:00", "Topic", 0),
        ]

        summary = _summarize(rows, datetime(2026, 3, 14).date(), 7)

        assert summary.topics[0].accuracy == 0.5
