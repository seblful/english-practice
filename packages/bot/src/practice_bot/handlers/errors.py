"""Last-resort error handling for the whole application."""

from practice_runtime.logging import get_logger
from telegram import Update
from telegram.ext import ContextTypes

from practice_bot.updates import Interaction

logger = get_logger(__name__)

UNEXPECTED_ERROR = "⚠️ Something went wrong on my side. Please try again."


async def report_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log an exception no handler caught, and apologise to the user."""
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
        await who.say(UNEXPECTED_ERROR)
    except Exception as exc:
        # Telling the user failed too; there is nowhere left to escalate.
        logger.warning("error_notice_failed", error=str(exc))
