"""The bot's handlers, and the one place they are registered.

Registration order matters: Telegram dispatches an update to the first handler
that claims it, so the catch-all text handler comes last.
"""

from typing import Any

from telegram.ext import (
    BaseHandler,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from practice_bot.callbacks import (
    ACTION_PATTERN,
    ADMIN_PATTERN,
    TOPIC_PATTERN,
)
from practice_bot.context import BotContext
from practice_bot.handlers import admin, answers, exercises, menu
from practice_bot.handlers.errors import report_error

__all__ = ["build_handlers", "report_error"]


def build_handlers() -> list[BaseHandler[Any, BotContext, None]]:
    """Return every handler the application should register.

    Returns:
        The handlers, in dispatch order.
    """
    return [
        CommandHandler("start", menu.start_command),
        CommandHandler("exercise", menu.exercise_command),
        CommandHandler("rule", menu.rule_command),
        CommandHandler("help", menu.help_command),
        CommandHandler("pending", admin.pending_command),
        CallbackQueryHandler(exercises.topic_selection, pattern=TOPIC_PATTERN),
        CallbackQueryHandler(exercises.exercise_action, pattern=ACTION_PATTERN),
        CallbackQueryHandler(admin.admin_action, pattern=ADMIN_PATTERN),
        MessageHandler(filters.TEXT & ~filters.COMMAND, answers.text_message),
    ]
