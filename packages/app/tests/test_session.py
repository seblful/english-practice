"""Tests for what the app remembers across lessons.

The lesson itself is :mod:`practice_core.lesson` now, and is tested through
its own interface in the core suite -- so what is left here is the one thing
only this front end keeps: the topic the home screen offers again.
"""

from practice_app.session import LESSON_LENGTH, PracticeSession


class TestPracticeSession:
    def test_it_starts_with_nothing_open(self) -> None:
        session = PracticeSession()

        assert session.lesson is None
        assert session.last_topic_id is None

    def test_beginning_a_topic_run_remembers_the_topic(self) -> None:
        session = PracticeSession()

        lesson = session.begin(1, "Present Tenses")

        assert session.lesson is lesson
        assert session.last_topic_id == 1
        assert session.last_topic_name == "Present Tenses"

    def test_a_run_is_a_lesson_long_by_default(self) -> None:
        session = PracticeSession()

        assert session.begin(1, "Present Tenses").length == LESSON_LENGTH

    def test_a_shorter_run_can_be_asked_for(self) -> None:
        """The screen draws its bar off the length, so it has to be settable."""
        session = PracticeSession()

        assert session.begin(1, "Present Tenses", length=3).length == 3

    def test_a_mixed_run_is_not_a_topic_to_return_to(self) -> None:
        session = PracticeSession()

        session.begin(None, "Mixed practice")

        assert session.last_topic_id is None
        assert session.last_topic_name is None

    def test_ending_keeps_the_topic_for_next_time(self) -> None:
        session = PracticeSession()
        session.begin(1, "Present Tenses")

        session.end()

        assert session.lesson is None
        assert session.last_topic_id == 1
        assert session.last_topic_name == "Present Tenses"
