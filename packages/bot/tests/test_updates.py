"""Tests for narrowing a Telegram update to an interaction."""

from unittest.mock import AsyncMock, Mock

from telegram import InaccessibleMessage, Update

from practice_bot import formatter
from practice_bot.updates import Interaction


class TestFromUpdate:
    """Tests for Interaction.from_update."""

    def test_text_message(self, mock_update: Mock, mock_message: AsyncMock) -> None:
        who = Interaction.from_update(mock_update)

        assert who is not None
        assert who.message is mock_message
        assert who.query is None
        assert who.callback_data == ""

    def test_callback_query(self, mock_callback_update: Mock) -> None:
        who = Interaction.from_update(mock_callback_update)

        assert who is not None
        assert who.query is mock_callback_update.callback_query
        assert who.callback_data == "topic:random"

    def test_update_without_user_is_rejected(self, mock_update: Mock) -> None:
        mock_update.effective_user = None

        assert Interaction.from_update(mock_update) is None

    def test_update_without_message_is_rejected(self, mock_update: Mock) -> None:
        mock_update.message = None

        assert Interaction.from_update(mock_update) is None

    def test_inaccessible_callback_message_is_rejected(
        self, mock_callback_update: Mock
    ) -> None:
        """A button on a message too old to act on cannot be replied to."""
        mock_callback_update.callback_query.message = Mock(spec=InaccessibleMessage)

        assert Interaction.from_update(mock_callback_update) is None

    def test_real_update_without_user(self) -> None:
        """The narrowing also holds for an actual Update instance."""
        assert Interaction.from_update(Update(update_id=1)) is None


class TestText:
    """Tests for the message text accessor."""

    def test_strips_surrounding_whitespace(self, mock_update: Mock) -> None:
        mock_update.message.text = "  is doing \n"
        who = Interaction.from_update(mock_update)

        assert who is not None
        assert who.text == "is doing"

    def test_missing_text_is_empty(self, mock_update: Mock) -> None:
        mock_update.message.text = None
        who = Interaction.from_update(mock_update)

        assert who is not None
        assert who.text == ""

    def test_callback_query_without_data(self, mock_callback_update: Mock) -> None:
        mock_callback_update.callback_query.data = None
        who = Interaction.from_update(mock_callback_update)

        assert who is not None
        assert who.callback_data == ""


class TestSaying:
    """A reply carries its own parse mode, so no call site has to remember it."""

    async def test_marked_up_text_is_sent_as_html(self, mock_update: Mock) -> None:
        who = Interaction.from_update(mock_update)
        assert who is not None

        await who.say(formatter.topic_line("Present Tenses"))

        assert mock_update.message.reply_text.await_args.kwargs["parse_mode"] == "HTML"

    async def test_a_plain_constant_is_sent_as_plain_text(
        self, mock_update: Mock
    ) -> None:
        """Adding the parse mode to a constant containing `<` gets a 400."""
        who = Interaction.from_update(mock_update)
        assert who is not None

        await who.say("Choose next exercise:")

        assert "parse_mode" not in mock_update.message.reply_text.await_args.kwargs

    async def test_the_caller_can_still_say_otherwise(self, mock_update: Mock) -> None:
        who = Interaction.from_update(mock_update)
        assert who is not None

        await who.say(formatter.topic_line("Present Tenses"), parse_mode=None)

        assert mock_update.message.reply_text.await_args.kwargs["parse_mode"] is None
