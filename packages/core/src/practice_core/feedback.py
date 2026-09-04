"""Wording for a grading result, and small fixes to the book's markdown."""

import random
import re
from collections.abc import Sequence

from practice_core.models import QuestionAnswer

__all__ = [
    "CORRECT_PHRASES",
    "WRONG_PHRASES",
    "full_answer_text",
    "short_answer_text",
    "to_markdown",
    "verdict_phrase",
]

CORRECT_PHRASES = (
    "Correct!",
    "Well done!",
    "Perfect!",
    "Great job!",
    "You nailed it!",
    "Excellent!",
    "Spot on!",
    "Brilliant!",
    "Bullseye!",
    "Awesome!",
)

WRONG_PHRASES = (
    "Not quite",
    "Almost there",
    "Close, but not quite",
    "Needs a little work",
    "Keep practicing!",
    "Don't give up!",
    "Learning opportunity!",
    "Take another look",
    "Good try!",
    "You'll get it next time!",
)

# The pipeline leaves the book's bullet glyphs, and no renderer knows them.
_BULLET_PATTERNS = (
    (re.compile(r"^- \[ \]\s*", re.MULTILINE), "- "),
    (re.compile(r"^[☐□•●]\s*", re.MULTILINE), "- "),
    (re.compile(r"^\*\s+", re.MULTILINE), "- "),
)


def verdict_phrase(is_correct: bool) -> str:
    """Return varied feedback on an answer."""
    return random.choice(CORRECT_PHRASES if is_correct else WRONG_PHRASES)


def to_markdown(text: str) -> str:
    """Normalize book text so a markdown renderer shows it as intended."""
    result = text.strip()
    for pattern, replacement in _BULLET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def short_answer_text(answers: Sequence[QuestionAnswer]) -> str:
    """Return the accepted short answers on one line."""
    return ", ".join(answer.short_answer for answer in answers)


def full_answer_text(answers: Sequence[QuestionAnswer], separator: str = "\n") -> str:
    """Return the accepted full sentences, one per line."""
    return separator.join(answer.full_answer for answer in answers)
