"""Access control, and the decorator that applies it."""

from collections.abc import Callable, Coroutine
from enum import StrEnum, auto
from functools import wraps
from typing import TYPE_CHECKING, Any

from practice_runtime.logging import get_logger
from telegram import InlineKeyboardMarkup, Update

from practice_bot import formatter
from practice_bot.context import BotContext, BotDependencies
from practice_bot.keyboards import access_request_keyboard
from practice_bot.updates import Interaction

if TYPE_CHECKING:
    from practice_bot.models.auth import AuthStatus

logger = get_logger(__name__)

InteractionHandler = Callable[[Interaction, BotContext], Coroutine[Any, Any, None]]
UpdateHandler = Callable[[Update, BotContext], Coroutine[Any, Any, None]]

PENDING_MESSAGE = "⏳ Your request has been sent to the admin for approval."
STILL_PENDING_MESSAGE = (
    "⏳ Your request is still pending. "
    "Please wait for the admin to approve your access."
)
REJECTED_NOTICE = "❌ Your access has been denied."
APPROVED_NOTICE = "✅ Your access has been approved! Use /start to begin practicing."
NOT_AUTHORIZED_MESSAGE = "🚫 You are not authorized to use this command."


class Access(StrEnum):
    """Who may reach a handler."""

    PUBLIC = auto()
    APPROVED = auto()
    ADMIN = auto()


async def _send(
    context: BotContext,
    chat_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Send an unsolicited message, in HTML when the text is HTML."""
    kwargs: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        kwargs["reply_markup"] = reply_markup
    if isinstance(text, formatter.Html):
        kwargs["parse_mode"] = "HTML"
    await context.bot.send_message(**kwargs)


async def notify_admin(
    context: BotContext,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Send a message to the admin, tolerating an unreachable admin chat."""
    admin_user_id = context.dependencies.admin_user_id
    if admin_user_id is None:
        return
    try:
        await _send(context, admin_user_id, text, reply_markup)
    except Exception as exc:
        # The admin may never have started a chat; the user's request must not fail.
        logger.warning(
            "admin_notify_failed",
            admin_user_id=admin_user_id,
            error=str(exc),
        )


async def notify_user(context: BotContext, user_id: int, text: str) -> None:
    """Send a message to a user, tolerating a blocked bot."""
    try:
        await _send(context, user_id, text)
    except Exception as exc:
        logger.warning("user_notify_failed", user_id=user_id, error=str(exc))


async def _request_access(who: Interaction, context: BotContext) -> None:
    """Queue an access request and tell both sides about it."""
    full_name = who.user.full_name or "Unknown"
    await who.say(PENDING_MESSAGE)

    await notify_admin(
        context,
        formatter.access_request(full_name, who.user.username, who.user.id),
        reply_markup=access_request_keyboard(who.user.id),
    )


async def ensure_approved(who: Interaction, context: BotContext) -> bool:
    """Check whether a user may use the bot, replying when they may not."""
    dependencies: BotDependencies = context.dependencies
    if not dependencies.access_control_enabled or dependencies.is_admin(who.user.id):
        return True

    status: AuthStatus | None = await context.users.get_auth_status(who.user.id)
    if status == "approved":
        return True

    full_name = who.user.full_name or "Unknown"
    if status is None:
        await context.users.register_user(who.user.id, full_name, who.user.username)
        logger.info("access_requested", user_id=who.user.id)
        await _request_access(who, context)
    elif status == "rejected":
        await context.users.reset_to_pending(who.user.id, full_name, who.user.username)
        logger.info("access_reapplied", user_id=who.user.id)
        await _request_access(who, context)
    else:
        await who.say(STILL_PENDING_MESSAGE)

    return False


async def ensure_admin(who: Interaction, context: BotContext) -> bool:
    """Check whether a user administers the bot, replying when they do not."""
    if context.dependencies.is_admin(who.user.id):
        return True
    logger.warning("admin_action_denied", user_id=who.user.id)
    await who.say(NOT_AUTHORIZED_MESSAGE)
    return False


def handler(
    access: Access = Access.APPROVED,
) -> Callable[[InteractionHandler], UpdateHandler]:
    """Adapt an interaction handler into a Telegram callback."""

    def decorate(func: InteractionHandler) -> UpdateHandler:
        @wraps(func)
        async def callback(update: Update, context: BotContext) -> None:
            who = Interaction.from_update(update)
            if who is None:
                logger.debug("update_ignored", update_id=update.update_id)
                return

            if who.query is not None:
                await who.query.answer()

            if access is Access.ADMIN and not await ensure_admin(who, context):
                return
            if access is Access.APPROVED and not await ensure_approved(who, context):
                return

            await func(who, context)

        return callback

    return decorate
