"""The bot's view of the practice content.

The models themselves live in :mod:`practice_core.models`, shared with the
Android app so that both front ends read the same book the same way. This
module is the bot's import surface for them: handlers, keyboards and the
formatter go on naming ``english_practice.models.book``, and the shared
definitions can move without a hundred imports following them.
"""

from practice_core.models import (
    ContentCounts,
    Exercise,
    Question,
    QuestionAnswer,
    Topic,
    Unit,
)

__all__ = [
    "ContentCounts",
    "Exercise",
    "Question",
    "QuestionAnswer",
    "Topic",
    "Unit",
]
