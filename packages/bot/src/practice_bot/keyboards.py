"""Inline keyboards: which buttons go together, and in what order."""

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
    """Offer the ways to start the next exercise."""
    rows = [
        [button("🎲 Random", KeywordChoice(TopicSelection.RANDOM))],
        [button("📚 New Topic", KeywordChoice(TopicSelection.NEW_TOPIC))],
    ]
    if has_previous_topic:
        rows.append([button("🔄 Same Topic", KeywordChoice(TopicSelection.SAME))])
    return InlineKeyboardMarkup(rows)


def topics_keyboard(topics: Sequence[Topic]) -> InlineKeyboardMarkup:
    """List every topic, one per row."""
    return InlineKeyboardMarkup(
        [[button(topic.name, SpecificTopic(topic.id))] for topic in topics]
    )


def exercise_keyboard() -> InlineKeyboardMarkup:
    """Offer the actions available while an exercise is open."""
    return InlineKeyboardMarkup([[button("📖 Show Unit", ExerciseAction.SHOW_UNIT)]])


def access_request_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Let the admin decide about one access request."""
    return InlineKeyboardMarkup(
        [
            [
                button("✅ Approve", AdminAction(AdminDecision.APPROVE, user_id)),
                button("❌ Reject", AdminAction(AdminDecision.REJECT, user_id)),
            ]
        ]
    )


def pending_users_keyboard(pending: Sequence[PendingUser]) -> InlineKeyboardMarkup:
    """Let the admin work through the approval queue."""
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
