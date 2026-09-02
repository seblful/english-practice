"""Typed inline-button payloads.

Telegram gives every inline button 64 bytes of opaque string, which the bot
receives back verbatim. Encoding and parsing live here, together with the
handler patterns, so the two can never drift: a keyboard cannot emit a payload
no handler is registered for.

Every ``parse`` returns ``None`` for anything unexpected. Old messages stay
clickable forever, so a payload from a previous version of the bot is a normal
event, not an error.
"""

from dataclasses import dataclass
from enum import StrEnum

TOPIC_PREFIX = "topic"
ACTION_PREFIX = "action"
ADMIN_PREFIX = "admin"

_ADMIN_PAYLOAD_PARTS = 3

TOPIC_PATTERN = f"^{TOPIC_PREFIX}:"
ACTION_PATTERN = f"^{ACTION_PREFIX}:"
ADMIN_PATTERN = f"^{ADMIN_PREFIX}:"


class TopicSelection(StrEnum):
    """Which entry of the topic menu was pressed."""

    RANDOM = "random"
    NEW_TOPIC = "new_topic"
    SAME = "same"
    SPECIFIC = "specific"


# SPECIFIC travels as the bare topic id, so it is not a keyword payload.
_KEYWORD_SELECTIONS = {
    selection.value: selection
    for selection in TopicSelection
    if selection is not TopicSelection.SPECIFIC
}


@dataclass(frozen=True, slots=True)
class TopicChoice:
    """A topic-menu press, with the chosen topic when there is one."""

    selection: TopicSelection
    topic_id: int | None = None

    def payload(self) -> str:
        """Return the callback payload for this choice."""
        if self.selection is TopicSelection.SPECIFIC:
            return f"{TOPIC_PREFIX}:{self.topic_id}"
        return f"{TOPIC_PREFIX}:{self.selection.value}"

    @classmethod
    def for_topic(cls, topic_id: int) -> "TopicChoice":
        """Return the choice that selects one specific topic.

        Args:
            topic_id: Topic database ID.

        Returns:
            The corresponding choice.
        """
        return cls(TopicSelection.SPECIFIC, topic_id)

    @classmethod
    def parse(cls, data: str) -> "TopicChoice | None":
        """Parse a topic callback payload.

        Args:
            data: The raw payload from Telegram.

        Returns:
            The choice, or ``None`` when the payload is not a topic choice.
        """
        prefix, _, value = data.partition(":")
        if prefix != TOPIC_PREFIX or not value:
            return None

        keyword = _KEYWORD_SELECTIONS.get(value)
        if keyword is not None:
            return cls(keyword)

        try:
            return cls.for_topic(int(value))
        except ValueError:
            return None


class ExerciseAction(StrEnum):
    """An action offered underneath an exercise image."""

    SHOW_UNIT = "show_unit"

    def payload(self) -> str:
        """Return the callback payload for this action."""
        return f"{ACTION_PREFIX}:{self.value}"

    @classmethod
    def parse(cls, data: str) -> "ExerciseAction | None":
        """Parse an exercise-action payload.

        Args:
            data: The raw payload from Telegram.

        Returns:
            The action, or ``None`` when the payload names no known action.
        """
        prefix, _, value = data.partition(":")
        if prefix != ACTION_PREFIX:
            return None
        try:
            return cls(value)
        except ValueError:
            return None


class AdminDecision(StrEnum):
    """The admin's verdict on an access request."""

    APPROVE = "approve"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class AdminAction:
    """An approve/reject press, naming the user it applies to."""

    decision: AdminDecision
    user_id: int

    def payload(self) -> str:
        """Return the callback payload for this action."""
        return f"{ADMIN_PREFIX}:{self.decision.value}:{self.user_id}"

    @classmethod
    def parse(cls, data: str) -> "AdminAction | None":
        """Parse an admin-action payload.

        Args:
            data: The raw payload from Telegram.

        Returns:
            The action, or ``None`` when the payload is malformed.
        """
        parts = data.split(":")
        if len(parts) != _ADMIN_PAYLOAD_PARTS or parts[0] != ADMIN_PREFIX:
            return None
        try:
            return cls(AdminDecision(parts[1]), int(parts[2]))
        except ValueError:
            return None
