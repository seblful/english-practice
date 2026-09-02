"""Tests for the assistant transcript store."""

from practice_bot.services.chat_history import ChatHistoryManager


class TestTranscripts:
    """Tests for recording and reading turns."""

    def test_empty_by_default(self) -> None:
        assert ChatHistoryManager().history(1, 1) == []

    def test_records_turns_in_order(self) -> None:
        history = ChatHistoryManager()

        history.add_turn(1, 1, "user", "why?")
        history.add_turn(1, 1, "assistant", "because")

        messages = history.history(1, 1)
        assert [(m.role, m.content) for m in messages] == [
            ("user", "why?"),
            ("assistant", "because"),
        ]

    def test_scoped_per_user_and_exercise(self) -> None:
        history = ChatHistoryManager()
        history.add_turn(1, 1, "user", "mine")

        assert history.history(2, 1) == []
        assert history.history(1, 2) == []

    def test_history_is_a_copy(self) -> None:
        """A caller mutating the returned list must not corrupt the store."""
        history = ChatHistoryManager()
        history.add_turn(1, 1, "user", "why?")

        history.history(1, 1).clear()

        assert len(history.history(1, 1)) == 1

    def test_exercises_are_kept_apart(self) -> None:
        history = ChatHistoryManager()
        history.add_turn(1, 7, "user", "hello")

        assert len(history.history(1, 7)) == 1
        assert history.history(1, 1) == []


class TestCapping:
    """Transcripts are capped so a long chat cannot grow without bound."""

    def test_oldest_turns_are_dropped(self) -> None:
        history = ChatHistoryManager(max_messages=3)

        for index in range(5):
            history.add_turn(1, 1, "user", f"message {index}")

        contents = [message.content for message in history.history(1, 1)]
        assert contents == ["message 2", "message 3", "message 4"]

    def test_cap_is_at_least_one(self) -> None:
        history = ChatHistoryManager(max_messages=0)

        history.add_turn(1, 1, "user", "first")
        history.add_turn(1, 1, "user", "second")

        assert [m.content for m in history.history(1, 1)] == ["second"]


class TestPruning:
    """Moving on from an exercise releases what it held."""

    def test_start_exercise_drops_other_exercises(self) -> None:
        history = ChatHistoryManager()
        history.add_turn(1, 1, "user", "about one")
        history.add_turn(1, 2, "user", "about two")

        history.start_exercise(1, 2)

        assert history.history(1, 1) == []
        assert len(history.history(1, 2)) == 1

    def test_start_exercise_on_an_unknown_user_is_a_no_op(self) -> None:
        ChatHistoryManager().start_exercise(1, 1)

    def test_start_exercise_with_no_prior_transcript(self) -> None:
        history = ChatHistoryManager()
        history.add_turn(1, 1, "user", "about one")

        history.start_exercise(1, 99)

        assert history.history(1, 1) == []
        assert history.history(1, 99) == []
        assert history._history == {}

    def test_forget_user_drops_everything(self) -> None:
        history = ChatHistoryManager()
        history.add_turn(1, 1, "user", "about one")

        history.forget_user(1)

        assert history.history(1, 1) == []

    def test_forget_unknown_user_is_a_no_op(self) -> None:
        ChatHistoryManager().forget_user(404)
