"""Access control, and the decorator that applies it.

Every handler in this package is wrapped by :func:`handler`, which narrows the
update, answers the callback query, and enforces the access level. A handler
therefore cannot forget its authorization check, and cannot be reached with an
update it is not equipped for.
"""

from collections.abc import Callable, Coroutine
from enum import StrEnum, auto
from functools import wraps
from typing import TYPE_CHECKING, Any

from telegram import InlineKeyboardMarkup, Update

from english_practice.bot import formatter
from english_practice.bot.context import BotContext, BotDependencies
from english_practice.bot.keyboards import access_request_keyboard
from english_practice.bot.updates import Interaction
from english_practice.logging import get_logger

if TYPE_CHECKING:
    from english_practice.models.auth import AuthStatus

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


async def notify_admin(
    context: BotContext,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Send a message to the admin, tolerating an unreachable admin chat.

    Args:
        context: The handler context.
        text: Message text in Telegram HTML.
        reply_markup: Optional keyboard to attach.
    """
    admin_user_id = context.dependencies.admin_user_id
    if admin_user_id is None:
        return
    try:
        await context.bot.send_message(
            chat_id=admin_user_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    except Exception as exc:
        # The admin may never have started a chat with the bot; that must not
        # break the request the user is waiting on.
        logger.warning(
            "admin_notify_failed",
            admin_user_id=admin_user_id,
            error=str(exc),
        )


async def notify_user(context: BotContext, user_id: int, text: str) -> None:
    """Send a plain message to a user, tolerating a blocked bot.

    Args:
        context: The handler context.
        user_id: Telegram user ID to notify.
        text: Message text.
    """
    try:
        await context.bot.send_message(chat_id=user_id, text=text)
    except Exception as exc:
        logger.warning("user_notify_failed", user_id=user_id, error=str(exc))


async def _request_access(who: Interaction, context: BotContext) -> None:
    """Queue an access request and tell both sides about it.

    Args:
        who: The user asking for access.
        context: The handler context.
    """
    full_name = who.user.full_name or "Unknown"
    await who.message.reply_text(PENDING_MESSAGE)

    await notify_admin(
        context,
        formatter.access_request(full_name, who.user.username, who.user.id),
        reply_markup=access_request_keyboard(who.user.id),
    )


async def ensure_approved(who: Interaction, context: BotContext) -> bool:
    """Check whether a user may use the bot, replying when they may not.

    A user unknown to the bot is enrolled as pending and the admin is asked to
    decide; a previously rejected user re-applies by messaging again.

    Args:
        who: The user behind the update.
        context: The handler context.

    Returns:
        ``True`` when the handler may proceed.
    """
    dependencies: BotDependencies = context.dependencies
    if not dependencies.access_control_enabled or dependencies.is_admin(who.user.id):
        return True

    status: AuthStatus | None = await context.repository.get_auth_status(who.user.id)
    if status == "approved":
        return True

    full_name = who.user.full_name or "Unknown"
    if status is None:
        await context.repository.register_user(
            who.user.id, full_name, who.user.username
        )
        logger.info("access_requested", user_id=who.user.id)
        await _request_access(who, context)
    elif status == "rejected":
        await context.repository.reset_to_pending(
            who.user.id, full_name, who.user.username
        )
        logger.info("access_reapplied", user_id=who.user.id)
        await _request_access(who, context)
    else:
        await who.message.reply_text(STILL_PENDING_MESSAGE)

    return False


async def ensure_admin(who: Interaction, context: BotContext) -> bool:
    """Check whether a user administers the bot, replying when they do not.

    Args:
        who: The user behind the update.
        context: The handler context.

    Returns:
        ``True`` when the handler may proceed.
    """
    if context.dependencies.is_admin(who.user.id):
        return True
    logger.warning("admin_action_denied", user_id=who.user.id)
    await who.message.reply_text(NOT_AUTHORIZED_MESSAGE)
    return False


def handler(
    access: Access = Access.APPROVED,
) -> Callable[[InteractionHandler], UpdateHandler]:
    """Adapt an interaction handler into a Telegram callback.

    The wrapper narrows the update, acknowledges the button press so the
    client stops showing a spinner, and enforces ``access``.

    Args:
        access: Who may reach the handler.

    Returns:
        A decorator producing a callback that Telegram handlers can register.
    """

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
