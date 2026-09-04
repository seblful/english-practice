"""Command handlers: /start, /exercise, /rule, /help."""

from practice_runtime.logging import get_logger

from practice_bot import commands, keyboards
from practice_bot.context import BotContext
from practice_bot.handlers.access import Access, handler
from practice_bot.updates import Interaction

logger = get_logger(__name__)

MENU_PROMPT = "Choose an option:"


def _welcome(first_name: str) -> str:
    """Compose the greeting for a user starting the bot."""
    return (
        f"👋 Welcome to Random Murphy's English Grammar, {first_name}!\n\n"
        "I'll help you practice English grammar with exercises from Murphy's "
        "book.\n\nChoose an option:"
    )


@handler()
async def start_command(who: Interaction, context: BotContext) -> None:
    """Greet the user and offer the exercise menu."""
    session = context.sessions.get(who.user.id)
    logger.info("bot_started", user_id=who.user.id)

    await who.say(
        _welcome(who.user.first_name),
        reply_markup=keyboards.main_menu_keyboard(session.has_previous_topic),
    )


@handler()
async def exercise_command(who: Interaction, context: BotContext) -> None:
    """Offer the exercise menu."""
    session = context.sessions.get(who.user.id)
    await who.say(
        MENU_PROMPT,
        reply_markup=keyboards.main_menu_keyboard(session.has_previous_topic),
    )


@handler()
async def rule_command(who: Interaction, context: BotContext) -> None:
    """Toggle whether grammar rules follow each answer."""
    enabled = context.sessions.toggle_show_rule(who.user.id)
    status = "enabled ✅" if enabled else "disabled ❌"
    await who.say(f"📋 Rule display is now {status}.")


@handler(Access.PUBLIC)
async def help_command(who: Interaction, context: BotContext) -> None:
    """Explain what the bot does and list its commands."""
    await who.say(
        commands.help_text(include_admin=context.dependencies.is_admin(who.user.id)),
    )
