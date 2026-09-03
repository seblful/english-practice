"""Inline keyboards: which buttons go together, and in what order.

What each button *means* is :mod:`practice_bot.callbacks` -- its prefix, its
payload, and the pattern that claims the press. This module only lays them
out, and reaches for `callbacks.button` rather than spelling
``callback_data=...payload()`` per row, so a button here cannot emit something
no handler is registered to parse.
"""

from collections.abc import Sequence

from practice_core.models import Topic
from telegram import InlineKeyboardMarkup

from practice_bot.callbacks import (
    AdminAction,
    AdminDecision,
    ExerciseAction,
    KeywordChoice,
    SpecificTopic,
    TopicSelection,
    button,
)
from practice_bot.models.auth import PendingUser


def main_menu_keyboard(has_previous_topic: bool) -> InlineKeyboardMarkup:
    """Offer the ways to start the next exercise.

    Args:
        has_previous_topic: Whether the user has practised a specific topic,
            which is what makes "Same Topic" meaningful.

    Returns:
        The keyboard.
    """
    rows = [
        [button("🎲 Random", KeywordChoice(TopicSelection.RANDOM))],
        [button("📚 New Topic", KeywordChoice(TopicSelection.NEW_TOPIC))],
    ]
    if has_previous_topic:
        rows.append([button("🔄 Same Topic", KeywordChoice(TopicSelection.SAME))])
    return InlineKeyboardMarkup(rows)


def topics_keyboard(topics: Sequence[Topic]) -> InlineKeyboardMarkup:
    """List every topic, one per row.

    Args:
        topics: Topics to offer.

    Returns:
        The keyboard.
    """
    return InlineKeyboardMarkup(
        [[button(topic.name, SpecificTopic(topic.id))] for topic in topics]
    )


def exercise_keyboard() -> InlineKeyboardMarkup:
    """Offer the actions available while an exercise is open.

    Returns:
        The keyboard.
    """
    return InlineKeyboardMarkup([[button("📖 Show Unit", ExerciseAction.SHOW_UNIT)]])


def access_request_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Let the admin decide about one access request.

    Args:
        user_id: Telegram ID of the user requesting access.

    Returns:
        The keyboard.
    """
    return InlineKeyboardMarkup(
        [
            [
                button("✅ Approve", AdminAction(AdminDecision.APPROVE, user_id)),
                button("❌ Reject", AdminAction(AdminDecision.REJECT, user_id)),
            ]
        ]
    )


def pending_users_keyboard(pending: Sequence[PendingUser]) -> InlineKeyboardMarkup:
    """Let the admin work through the approval queue.

    Args:
        pending: Users awaiting a decision.

    Returns:
        The keyboard, one row per user.
    """
    return InlineKeyboardMarkup(
        [
            [
                button(
                    f"✅ {user.label}",
                    AdminAction(AdminDecision.APPROVE, user.telegram_id),
                ),
                button(
                    "❌ Reject",
                    AdminAction(AdminDecision.REJECT, user.telegram_id),
                ),
            ]
            for user in pending
        ]
    )
