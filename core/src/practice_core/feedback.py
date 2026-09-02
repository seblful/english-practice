"""Wording for a grading result, and small fixes to the book's markdown.

The phrases are stored plain. The bot wraps them in Telegram HTML and the app
hands them to a Material widget, so neither markup belongs here — but the words
do, so that praise and consolation read the same on both.
"""

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

# The extraction pipeline leaves the book's own bullet glyphs in the rules, and
# neither renderer knows them.
_BULLET_PATTERNS = (
    (re.compile(r"^- \[ \]\s*", re.MULTILINE), "- "),
    (re.compile(r"^[☐□•●]\s*", re.MULTILINE), "- "),
    (re.compile(r"^\*\s+", re.MULTILINE), "- "),
)


def verdict_phrase(is_correct: bool) -> str:
    """Return varied feedback on an answer.

    Args:
        is_correct: Whether the answer was correct.

    Returns:
        One phrase, chosen at random so a practice run does not read the same
        line twenty times.
    """
    return random.choice(CORRECT_PHRASES if is_correct else WRONG_PHRASES)


def to_markdown(text: str) -> str:
    """Normalize book text so a markdown renderer shows it as intended.

    Args:
        text: Raw text from the database.

    Returns:
        The same text with its bullets in dash form and no surrounding blanks.
    """
    result = text.strip()
    for pattern, replacement in _BULLET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def short_answer_text(answers: Sequence[QuestionAnswer]) -> str:
    """Return the accepted short answers on one line.

    Args:
        answers: The answers to show.

    Returns:
        The joined text; empty when there is nothing to show.
    """
    return ", ".join(answer.short_answer for answer in answers)


def full_answer_text(answers: Sequence[QuestionAnswer], separator: str = "\n") -> str:
    """Return the accepted full sentences, one per line.

    Args:
        answers: The answers to show.
        separator: What to put between them. The bot uses a single newline
            inside a preformatted block; the app uses a blank line, because a
            markdown renderer treats a single newline as a soft wrap.

    Returns:
        The joined text; empty when there is nothing to show.
    """
    return separator.join(answer.full_answer for answer in answers)
