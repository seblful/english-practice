"""Typed inline-button payloads, and what each family of them means."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from telegram import InlineKeyboardButton

__all__ = [
    "ACTIONS",
    "ADMIN",
    "TOPICS",
    "AdminAction",
    "AdminDecision",
    "ExerciseAction",
    "Family",
    "KeywordChoice",
    "Payload",
    "SpecificTopic",
    "TopicChoice",
    "TopicSelection",
    "button",
    "parse_topic_choice",
]

TOPIC_PREFIX = "topic"
ACTION_PREFIX = "action"
ADMIN_PREFIX = "admin"

_ADMIN_PAYLOAD_PARTS = 3


class Payload(Protocol):
    """Anything that can be encoded into a button's callback data."""

    def payload(self) -> str:
        """Return the callback payload."""
        ...


def button(label: str, choice: Payload) -> InlineKeyboardButton:
    """Return the button that emits one payload."""
    return InlineKeyboardButton(label, callback_data=choice.payload())


@dataclass(frozen=True, slots=True)
class Family[T]:
    """One prefix, the pattern that claims it, and how to read its payloads."""

    prefix: str
    parse: Callable[[str], T | None]

    @property
    def pattern(self) -> str:
        """Return the regex a ``CallbackQueryHandler`` registers for."""
        return f"^{self.prefix}:"


class TopicSelection(StrEnum):
    """A topic-menu entry that names no particular topic."""

    RANDOM = "random"
    NEW_TOPIC = "new_topic"
    SAME = "same"


_KEYWORD_SELECTIONS = {selection.value: selection for selection in TopicSelection}


@dataclass(frozen=True, slots=True)
class KeywordChoice:
    """A topic-menu press that stands on its own, with no topic to carry."""

    selection: TopicSelection

    def payload(self) -> str:
        """Return the callback payload for this choice."""
        return f"{TOPIC_PREFIX}:{self.selection.value}"


@dataclass(frozen=True, slots=True)
class SpecificTopic:
    """A press on one named topic, which travels as the bare topic id."""

    topic_id: int

    def payload(self) -> str:
        """Return the callback payload for this choice."""
        return f"{TOPIC_PREFIX}:{self.topic_id}"


# Split in two so "a specific topic" cannot exist without saying which.
type TopicChoice = KeywordChoice | SpecificTopic


def parse_topic_choice(data: str) -> TopicChoice | None:
    """Parse a topic callback payload."""
    prefix, _, value = data.partition(":")
    if prefix != TOPIC_PREFIX or not value:
        return None

    keyword = _KEYWORD_SELECTIONS.get(value)
    if keyword is not None:
        return KeywordChoice(keyword)

    try:
        return SpecificTopic(int(value))
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
        """Parse an exercise-action payload."""
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
        """Parse an admin-action payload."""
        parts = data.split(":")
        if len(parts) != _ADMIN_PAYLOAD_PARTS or parts[0] != ADMIN_PREFIX:
            return None
        try:
            return cls(AdminDecision(parts[1]), int(parts[2]))
        except ValueError:
            return None


#: The three families of inline button, registered and parsed from one place.
TOPICS: Family[TopicChoice] = Family(prefix=TOPIC_PREFIX, parse=parse_topic_choice)
ACTIONS: Family[ExerciseAction] = Family(
    prefix=ACTION_PREFIX, parse=ExerciseAction.parse
)
ADMIN: Family[AdminAction] = Family(prefix=ADMIN_PREFIX, parse=AdminAction.parse)
