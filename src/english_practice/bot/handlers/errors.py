"""Last-resort error handling for the whole application."""

from telegram import Update
from telegram.ext import ContextTypes

from english_practice.bot.updates import Interaction
from english_practice.logging import get_logger

logger = get_logger(__name__)

UNEXPECTED_ERROR = "⚠️ Something went wrong on my side. Please try again."


async def report_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log an exception no handler caught, and apologise to the user.

    Registered with ``Application.add_error_handler``, this is what keeps an
    unforeseen failure from leaving the user staring at silence.

    Args:
        update: The update being processed, when there was one.
        context: The context carrying ``error``.
    """
    logger.error(
        "unhandled_error",
        error=str(context.error),
        exc_info=context.error,
    )

    if not isinstance(update, Update):
        return

    who = Interaction.from_update(update)
    if who is None:
        return

    try:
        await who.message.reply_text(UNEXPECTED_ERROR)
    except Exception as exc:
        # Telling the user failed too; there is nowhere left to escalate.
        logger.warning("error_notice_failed", error=str(exc))
