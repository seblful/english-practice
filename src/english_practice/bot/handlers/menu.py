"""Command handlers: /start, /exercise, /rule, /help."""

from english_practice.bot import commands, keyboards
from english_practice.bot.context import BotContext
from english_practice.bot.handlers.access import Access, handler
from english_practice.bot.updates import Interaction
from english_practice.logging import get_logger

logger = get_logger(__name__)

MENU_PROMPT = "Choose an option:"


def _welcome(first_name: str) -> str:
    """Compose the greeting for a user starting the bot.

    Args:
        first_name: The user's first name as Telegram reports it.

    Returns:
        The message text.
    """
    return (
        f"👋 Welcome to Random Murphy's English Grammar, {first_name}!\n\n"
        "I'll help you practice English grammar with exercises from Murphy's "
        "book.\n\nChoose an option:"
    )


@handler()
async def start_command(who: Interaction, context: BotContext) -> None:
    """Greet the user and offer the exercise menu.

    Args:
        who: The user behind the update.
        context: The handler context.
    """
    session = context.sessions.get(who.user.id)
    logger.info("bot_started", user_id=who.user.id)

    await who.message.reply_text(
        _welcome(who.user.first_name),
        reply_markup=keyboards.main_menu_keyboard(session.has_previous_topic),
    )


@handler()
async def exercise_command(who: Interaction, context: BotContext) -> None:
    """Offer the exercise menu.

    Args:
        who: The user behind the update.
        context: The handler context.
    """
    session = context.sessions.get(who.user.id)
    await who.message.reply_text(
        MENU_PROMPT,
        reply_markup=keyboards.main_menu_keyboard(session.has_previous_topic),
    )


@handler()
async def rule_command(who: Interaction, context: BotContext) -> None:
    """Toggle whether grammar rules follow each answer.

    Args:
        who: The user behind the update.
        context: The handler context.
    """
    enabled = context.sessions.toggle_show_rule(who.user.id)
    status = "enabled ✅" if enabled else "disabled ❌"
    await who.message.reply_text(f"📋 Rule display is now {status}.")


@handler(Access.PUBLIC)
async def help_command(who: Interaction, context: BotContext) -> None:
    """Explain what the bot does and list its commands.

    Help stays public: someone waiting for approval should still be able to
    find out what they are waiting for.

    Args:
        who: The user behind the update.
        context: The handler context.
    """
    await who.message.reply_text(
        commands.help_text(include_admin=context.dependencies.is_admin(who.user.id)),
        parse_mode="HTML",
    )
