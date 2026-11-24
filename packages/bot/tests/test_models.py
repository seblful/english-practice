"""Tests for the bot's own models: who may use it."""

from practice_bot.models.auth import PendingUser


class TestPendingUser:
    """The access-request model — the one content model that is the bot's own."""

    def test_label_includes_the_username(self) -> None:
        user = PendingUser(telegram_id=1, full_name="Alice", telegram_username="alice")

        assert user.label == "Alice (@alice)"

    def test_label_without_a_username(self) -> None:
        assert PendingUser(telegram_id=1, full_name="Alice").label == "Alice"
