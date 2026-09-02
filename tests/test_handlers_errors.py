"""Tests for the application-wide error handler."""

from unittest.mock import Mock

from telegram import Update

from english_practice.bot.handlers.errors import UNEXPECTED_ERROR, report_error


class TestReportError:
    """Tests for reporting an exception no handler caught."""

    async def test_apologises_to_the_user(
        self, mock_update: Mock, mock_context: Mock
    ) -> None:
        mock_context.error = RuntimeError("boom")

        await report_error(mock_update, mock_context)

        mock_update.message.reply_text.assert_awaited_once_with(UNEXPECTED_ERROR)

    async def test_handles_an_error_without_an_update(self, mock_context: Mock) -> None:
        mock_context.error = RuntimeError("boom")

        await report_error(None, mock_context)

    async def test_handles_an_update_it_cannot_reply_to(
        self, mock_context: Mock
    ) -> None:
        mock_context.error = RuntimeError("boom")

        await report_error(Update(update_id=1), mock_context)

    async def test_survives_a_failing_reply(
        self, mock_update: Mock, mock_context: Mock
    ) -> None:
        mock_context.error = RuntimeError("boom")
        mock_update.message.reply_text.side_effect = RuntimeError("network")

        await report_error(mock_update, mock_context)
