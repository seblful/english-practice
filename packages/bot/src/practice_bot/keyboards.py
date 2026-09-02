"""Inline keyboards.

Buttons carry payloads built by :mod:`practice_bot.callbacks`, so a
button can only ever emit something a handler is registered to parse.
"""

from collections.abc import Sequence

from practice_core.models import Topic
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from practice_bot.callbacks import (
    AdminAction,
    AdminDecision,
    ExerciseAction,
    KeywordChoice,
    SpecificTopic,
    TopicSelection,
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
        [
            InlineKeyboardButton(
                "🎲 Random",
                callback_data=KeywordChoice(TopicSelection.RANDOM).payload(),
            )
        ],
        [
            InlineKeyboardButton(
                "📚 New Topic",
                callback_data=KeywordChoice(TopicSelection.NEW_TOPIC).payload(),
            )
        ],
    ]
    if has_previous_topic:
        rows.append(
            [
                InlineKeyboardButton(
                    "🔄 Same Topic",
                    callback_data=KeywordChoice(TopicSelection.SAME).payload(),
                )
            ]
        )
    return InlineKeyboardMarkup(rows)


def topics_keyboard(topics: Sequence[Topic]) -> InlineKeyboardMarkup:
    """List every topic, one per row.

    Args:
        topics: Topics to offer.

    Returns:
        The keyboard.
    """
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    topic.name,
                    callback_data=SpecificTopic(topic.id).payload(),
                )
            ]
            for topic in topics
        ]
    )


def exercise_keyboard() -> InlineKeyboardMarkup:
    """Offer the actions available while an exercise is open.

    Returns:
        The keyboard.
    """
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📖 Show Unit",
                    callback_data=ExerciseAction.SHOW_UNIT.payload(),
                )
            ]
        ]
    )


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
                InlineKeyboardButton(
                    "✅ Approve",
                    callback_data=AdminAction(AdminDecision.APPROVE, user_id).payload(),
                ),
                InlineKeyboardButton(
                    "❌ Reject",
                    callback_data=AdminAction(AdminDecision.REJECT, user_id).payload(),
                ),
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
                InlineKeyboardButton(
                    f"✅ {user.label}",
                    callback_data=AdminAction(
                        AdminDecision.APPROVE, user.telegram_id
                    ).payload(),
                ),
                InlineKeyboardButton(
                    "❌ Reject",
                    callback_data=AdminAction(
                        AdminDecision.REJECT, user.telegram_id
                    ).payload(),
                ),
            ]
            for user in pending
        ]
    )
