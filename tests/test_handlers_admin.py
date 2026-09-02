"""Tests for the admin handlers."""

from collections.abc import Callable
from unittest.mock import Mock

import pytest

from english_practice.bot.handlers import admin
from english_practice.bot.handlers.access import APPROVED_NOTICE, REJECTED_NOTICE
from english_practice.bot.states import ActiveExercise
from english_practice.models.book import Exercise
from tests.conftest import USER_ID, replies


@pytest.fixture(autouse=True)
def _as_admin(set_admin: Callable[[int], None]) -> None:
    """Run every test in this module as the configured admin."""
    set_admin(USER_ID)


class TestPendingCommand:
    """Tests for /pending."""

    async def test_lists_the_queue(self, mock_update: Mock, mock_context: Mock) -> None:
        await admin.pending_command(mock_update, mock_context)

        call = mock_update.message.reply_text.call_args
        assert "Pending users (2)" in call.args[0]
        assert len(call.kwargs["reply_markup"].inline_keyboard) == 2

    async def test_reports_an_empty_queue(
        self, mock_update: Mock, mock_context: Mock
    ) -> None:
        mock_context.repository.list_pending_users.return_value = []

        await admin.pending_command(mock_update, mock_context)

        assert replies(mock_update.message) == [admin.NO_PENDING_MESSAGE]


class TestAdminAction:
    """Tests for approving and rejecting."""

    async def test_approve_records_and_notifies(
        self, mock_callback_update: Mock, mock_context: Mock
    ) -> None:
        mock_callback_update.callback_query.data = "admin:approve:111"

        await admin.admin_action(mock_callback_update, mock_context)

        mock_context.repository.set_auth_status.assert_awaited_once_with(
            111, "approved", USER_ID
        )
        mock_context.bot.send_message.assert_awaited_once_with(
            chat_id=111, text=APPROVED_NOTICE
        )

    async def test_reject_records_and_notifies(
        self, mock_callback_update: Mock, mock_context: Mock
    ) -> None:
        mock_callback_update.callback_query.data = "admin:reject:111"

        await admin.admin_action(mock_callback_update, mock_context)

        mock_context.repository.set_auth_status.assert_awaited_once_with(
            111, "rejected", USER_ID
        )
        mock_context.bot.send_message.assert_awaited_once_with(
            chat_id=111, text=REJECTED_NOTICE
        )

    async def test_shows_what_is_left_in_the_queue(
        self, mock_callback_update: Mock, mock_context: Mock
    ) -> None:
        mock_callback_update.callback_query.data = "admin:approve:111"

        await admin.admin_action(mock_callback_update, mock_context)

        texts = replies(mock_callback_update.callback_query.message)
        assert "has been ✅ approved" in texts[0]
        assert "Remaining pending (2)" in texts[1]

    async def test_says_nothing_more_when_the_queue_empties(
        self, mock_callback_update: Mock, mock_context: Mock
    ) -> None:
        mock_callback_update.callback_query.data = "admin:approve:111"
        mock_context.repository.list_pending_users.return_value = []

        await admin.admin_action(mock_callback_update, mock_context)

        assert len(replies(mock_callback_update.callback_query.message)) == 1

    async def test_unreachable_user_does_not_break_the_decision(
        self, mock_callback_update: Mock, mock_context: Mock
    ) -> None:
        """Someone who blocked the bot can still be approved."""
        mock_callback_update.callback_query.data = "admin:approve:111"
        mock_context.bot.send_message.side_effect = RuntimeError("blocked")

        await admin.admin_action(mock_callback_update, mock_context)

        mock_context.repository.set_auth_status.assert_awaited_once()

    async def test_rejecting_drops_the_users_state(
        self, mock_callback_update: Mock, mock_context: Mock, exercise: Exercise
    ) -> None:
        """A user who may no longer practise keeps nothing in memory."""
        mock_context.sessions.start_exercise(
            111,
            ActiveExercise(
                exercise=exercise,
                question=exercise.questions[0],
                topic_id=1,
                topic_name="Present Tenses",
            ),
        )
        mock_callback_update.callback_query.data = "admin:reject:111"

        await admin.admin_action(mock_callback_update, mock_context)

        assert len(mock_context.sessions) == 0
        mock_context.agents.forget_user.assert_called_once_with(111)

    async def test_approving_keeps_the_users_state(
        self, mock_callback_update: Mock, mock_context: Mock
    ) -> None:
        mock_context.sessions.get(111)
        mock_callback_update.callback_query.data = "admin:approve:111"

        await admin.admin_action(mock_callback_update, mock_context)

        assert len(mock_context.sessions) == 1
        mock_context.agents.forget_user.assert_not_called()

    async def test_malformed_payload_is_ignored(
        self, mock_callback_update: Mock, mock_context: Mock
    ) -> None:
        mock_callback_update.callback_query.data = "admin:approve:nobody"

        await admin.admin_action(mock_callback_update, mock_context)

        mock_context.repository.set_auth_status.assert_not_called()
        mock_callback_update.callback_query.message.reply_text.assert_not_called()
