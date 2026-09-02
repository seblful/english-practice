"""Tests for the command handlers."""

from collections.abc import Callable
from unittest.mock import Mock

from practice_bot.handlers import menu
from tests.conftest import ADMIN_ID, USER_ID, last_reply


class TestStartCommand:
    """Tests for /start."""

    async def test_greets_the_user_by_name(
        self, mock_update: Mock, mock_context: Mock
    ) -> None:
        await menu.start_command(mock_update, mock_context)

        text, _ = last_reply(mock_update.message)
        assert "Welcome" in text
        assert "Test" in text

    async def test_offers_two_options_to_a_new_user(
        self, mock_update: Mock, mock_context: Mock
    ) -> None:
        await menu.start_command(mock_update, mock_context)

        _, kwargs = last_reply(mock_update.message)
        assert len(kwargs["reply_markup"].inline_keyboard) == 2

    async def test_offers_same_topic_to_a_returning_user(
        self, mock_update: Mock, mock_context: Mock
    ) -> None:
        mock_context.sessions.get(USER_ID).last_topic_id = 1

        await menu.start_command(mock_update, mock_context)

        _, kwargs = last_reply(mock_update.message)
        assert len(kwargs["reply_markup"].inline_keyboard) == 3


class TestExerciseCommand:
    """Tests for /exercise."""

    async def test_shows_the_menu(self, mock_update: Mock, mock_context: Mock) -> None:
        await menu.exercise_command(mock_update, mock_context)

        text, kwargs = last_reply(mock_update.message)
        assert text == menu.MENU_PROMPT
        assert kwargs["reply_markup"] is not None


class TestRuleCommand:
    """Tests for /rule."""

    async def test_turns_rules_off(self, mock_update: Mock, mock_context: Mock) -> None:
        await menu.rule_command(mock_update, mock_context)

        assert mock_context.sessions.get(USER_ID).show_rule is False
        assert "disabled" in last_reply(mock_update.message)[0]

    async def test_turns_rules_back_on(
        self, mock_update: Mock, mock_context: Mock
    ) -> None:
        mock_context.sessions.get(USER_ID).show_rule = False

        await menu.rule_command(mock_update, mock_context)

        assert mock_context.sessions.get(USER_ID).show_rule is True
        assert "enabled" in last_reply(mock_update.message)[0]


class TestHelpCommand:
    """Tests for /help."""

    async def test_lists_the_public_commands(
        self, mock_update: Mock, mock_context: Mock
    ) -> None:
        await menu.help_command(mock_update, mock_context)

        text, kwargs = last_reply(mock_update.message)
        assert "/start" in text
        assert "/rule" in text
        assert "/pending" not in text
        assert kwargs["parse_mode"] == "HTML"

    async def test_lists_admin_commands_for_the_admin(
        self, mock_update: Mock, mock_context: Mock, set_admin: Callable[[int], None]
    ) -> None:
        set_admin(USER_ID)

        await menu.help_command(mock_update, mock_context)

        assert "/pending" in last_reply(mock_update.message)[0]

    async def test_hides_admin_commands_from_others(
        self, mock_update: Mock, mock_context: Mock, set_admin: Callable[[int], None]
    ) -> None:
        set_admin(ADMIN_ID)
        mock_context.repository.get_auth_status.return_value = "approved"

        await menu.help_command(mock_update, mock_context)

        assert "/pending" not in last_reply(mock_update.message)[0]
