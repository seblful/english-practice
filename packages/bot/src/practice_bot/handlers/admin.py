"""Admin handlers: reviewing and deciding access requests."""

from practice_runtime.logging import get_logger

from practice_bot import keyboards
from practice_bot.callbacks import ADMIN, AdminDecision
from practice_bot.context import BotContext
from practice_bot.handlers.access import (
    APPROVED_NOTICE,
    REJECTED_NOTICE,
    Access,
    handler,
    notify_user,
)
from practice_bot.updates import Interaction

logger = get_logger(__name__)

NO_PENDING_MESSAGE = "No pending users at the moment."


@handler(Access.ADMIN)
async def pending_command(who: Interaction, context: BotContext) -> None:
    """List everyone waiting for a decision.

    Args:
        who: The admin behind the update.
        context: The handler context.
    """
    pending = await context.users.list_pending_users()
    if not pending:
        await who.say(NO_PENDING_MESSAGE)
        return

    await who.say(
        f"📋 Pending users ({len(pending)}):",
        reply_markup=keyboards.pending_users_keyboard(pending),
    )


@handler(Access.ADMIN)
async def admin_action(who: Interaction, context: BotContext) -> None:
    """Approve or reject one access request, then show what is left.

    Args:
        who: The admin behind the update.
        context: The handler context.
    """
    action = ADMIN.parse(who.callback_data)
    if action is None:
        logger.warning("unparsable_admin_callback", data=who.callback_data)
        return

    approved = action.decision is AdminDecision.APPROVE
    await context.users.set_auth_status(
        action.user_id,
        "approved" if approved else "rejected",
        who.user.id,
    )
    if not approved:
        # Someone who may no longer use the bot should keep nothing in memory.
        context.forget_user(action.user_id)
    logger.info(
        "access_decided",
        target_user_id=action.user_id,
        decision=action.decision.value,
        admin_user_id=who.user.id,
    )

    verdict = "✅ approved" if approved else "❌ rejected"
    await who.say(f"User {action.user_id} has been {verdict}.")
    await notify_user(
        context,
        action.user_id,
        APPROVED_NOTICE if approved else REJECTED_NOTICE,
    )

    remaining = await context.users.list_pending_users()
    if remaining:
        await who.say(
            f"📋 Remaining pending ({len(remaining)}):",
            reply_markup=keyboards.pending_users_keyboard(remaining),
        )
