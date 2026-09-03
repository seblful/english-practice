"""Tests for access control and the handler decorator."""

from collections.abc import Callable
from unittest.mock import Mock

from telegram import Update

from practice_bot.handlers import menu
from practice_bot.handlers.access import (
    NOT_AUTHORIZED_MESSAGE,
    Access,
    handler,
    notify_admin,
    notify_user,
)
from practice_bot.handlers.admin import pending_command
from practice_bot.updates import Interaction
from tests.conftest import ADMIN_ID, USER_ID, replies


class TestAccessDisabled:
    """With no admin configured the bot is open to everyone."""

    async def test_handler_runs(self, mock_update: Mock, mock_context: Mock) -> None:
        await menu.start_command(mock_update, mock_context)

        assert "Welcome" in replies(mock_update.message)[0]
        mock_context.users.get_auth_status.assert_not_called()


class TestAccessEnabled:
    """With an admin configured, only approved users get through."""

    async def test_admin_is_always_allowed(
        self, mock_update: Mock, mock_context: Mock, set_admin: Callable[[int], None]
    ) -> None:
        set_admin(USER_ID)

        await menu.start_command(mock_update, mock_context)

        assert "Welcome" in replies(mock_update.message)[0]
        mock_context.users.get_auth_status.assert_not_called()

    async def test_approved_user_is_allowed(
        self, mock_update: Mock, mock_context: Mock, set_admin: Callable[[int], None]
    ) -> None:
        set_admin(ADMIN_ID)
        mock_context.users.get_auth_status.return_value = "approved"

        await menu.start_command(mock_update, mock_context)

        assert "Welcome" in replies(mock_update.message)[0]

    async def test_unknown_user_is_enrolled_and_admin_notified(
        self, mock_update: Mock, mock_context: Mock, set_admin: Callable[[int], None]
    ) -> None:
        set_admin(ADMIN_ID)
        mock_context.users.get_auth_status.return_value = None

        await menu.start_command(mock_update, mock_context)

        mock_context.users.register_user.assert_awaited_once_with(
            USER_ID, "Test User", "testuser"
        )
        assert "approval" in replies(mock_update.message)[0]
        mock_context.bot.send_message.assert_awaited_once()
        assert mock_context.bot.send_message.await_args.kwargs["chat_id"] == ADMIN_ID

    async def test_pending_user_is_told_to_wait(
        self, mock_update: Mock, mock_context: Mock, set_admin: Callable[[int], None]
    ) -> None:
        set_admin(ADMIN_ID)
        mock_context.users.get_auth_status.return_value = "pending"

        await menu.start_command(mock_update, mock_context)

        assert "still pending" in replies(mock_update.message)[0]
        mock_context.users.register_user.assert_not_called()
        mock_context.bot.send_message.assert_not_called()

    async def test_rejected_user_reapplies(
        self, mock_update: Mock, mock_context: Mock, set_admin: Callable[[int], None]
    ) -> None:
        set_admin(ADMIN_ID)
        mock_context.users.get_auth_status.return_value = "rejected"

        await menu.start_command(mock_update, mock_context)

        mock_context.users.reset_to_pending.assert_awaited_once_with(
            USER_ID, "Test User", "testuser"
        )
        assert "approval" in replies(mock_update.message)[0]

    async def test_unnamed_user_is_recorded_as_unknown(
        self, mock_update: Mock, mock_context: Mock, set_admin: Callable[[int], None]
    ) -> None:
        set_admin(ADMIN_ID)
        mock_update.effective_user.full_name = None

        await menu.start_command(mock_update, mock_context)

        mock_context.users.register_user.assert_awaited_once_with(
            USER_ID, "Unknown", "testuser"
        )

    async def test_public_handler_bypasses_approval(
        self, mock_update: Mock, mock_context: Mock, set_admin: Callable[[int], None]
    ) -> None:
        """A user waiting for approval can still read /help."""
        set_admin(ADMIN_ID)
        mock_context.users.get_auth_status.return_value = "pending"

        await menu.help_command(mock_update, mock_context)

        assert "How this works" in replies(mock_update.message)[0]


class TestAdminAccess:
    """Admin-only handlers refuse everybody else."""

    async def test_non_admin_is_refused(
        self, mock_update: Mock, mock_context: Mock, set_admin: Callable[[int], None]
    ) -> None:
        set_admin(ADMIN_ID)

        await pending_command(mock_update, mock_context)

        assert replies(mock_update.message) == [NOT_AUTHORIZED_MESSAGE]
        mock_context.users.list_pending_users.assert_not_called()

    async def test_refused_when_no_admin_is_configured(
        self, mock_update: Mock, mock_context: Mock
    ) -> None:
        await pending_command(mock_update, mock_context)

        assert replies(mock_update.message) == [NOT_AUTHORIZED_MESSAGE]


class TestDecorator:
    """Tests for the wrapper that adapts handlers to Telegram."""

    async def test_unusable_update_is_ignored(self, mock_context: Mock) -> None:
        called = False

        @handler(Access.PUBLIC)
        async def target(who: Interaction, context: object) -> None:
            nonlocal called
            called = True

        await target(Update(update_id=1), mock_context)

        assert called is False

    async def test_callback_query_is_acknowledged(
        self, mock_callback_update: Mock, mock_context: Mock
    ) -> None:
        @handler(Access.PUBLIC)
        async def target(who: Interaction, context: object) -> None:
            return None

        await target(mock_callback_update, mock_context)

        mock_callback_update.callback_query.answer.assert_awaited_once()

    async def test_docstring_and_name_are_preserved(self) -> None:
        assert menu.start_command.__name__ == "start_command"
        assert menu.start_command.__doc__ is not None


class TestNotifications:
    """Notifying a user must never break the flow that triggered it."""

    async def test_admin_notification_failure_is_swallowed(
        self, mock_context: Mock, set_admin: Callable[[int], None]
    ) -> None:
        set_admin(ADMIN_ID)
        mock_context.bot.send_message.side_effect = RuntimeError("blocked")

        await notify_admin(mock_context, "hello")

    async def test_no_admin_means_no_message(self, mock_context: Mock) -> None:
        await notify_admin(mock_context, "hello")

        mock_context.bot.send_message.assert_not_called()

    async def test_user_notification_failure_is_swallowed(
        self, mock_context: Mock
    ) -> None:
        mock_context.bot.send_message.side_effect = RuntimeError("blocked")

        await notify_user(mock_context, 1, "hello")
