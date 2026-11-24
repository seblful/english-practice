"""The gaps a full answer marks, and a short answer that covers all of them."""

import re
from typing import Final

__all__ = [
    "GAP_SEPARATOR",
    "NO_WORD",
    "complete_short_answer",
    "gaps",
    "missing_gaps",
]

# The book's own notation in its answer key.
GAP_SEPARATOR: Final = " … "
NO_WORD: Final = "—"

# One gap needs no covering: the short answer may rightly differ from it.
_SEVERAL_GAPS: Final = 2

_GAP: Final = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_APOSTROPHES: Final = str.maketrans(
    {"\N{RIGHT SINGLE QUOTATION MARK}": "'", "\N{LEFT SINGLE QUOTATION MARK}": "'"}
)


def gaps(full_answer: str) -> list[str]:
    """Return the bolded gaps of a full answer, in order."""
    return [gap.strip() for gap in _GAP.findall(full_answer) if gap.strip()]


def _comparable(text: str) -> str:
    """Return text with the differences that are not words taken out."""
    return " ".join(text.translate(_APOSTROPHES).split()).strip(" .,!?").casefold()


def _is_choice(short_answer: str) -> bool:
    """Whether a short answer is a letter picked from a list in the exercise."""
    letter = short_answer.strip()
    return len(letter) == 1 and letter.isalpha()


def missing_gaps(short_answer: str, full_answer: str) -> list[str]:
    """Return the gaps of a multi-gap full answer that its short answer leaves out.

    A single gap is not checked: there the short answer may rightly differ, as
    "OK" for a sentence that needs no change, or a letter naming an option.
    """
    found = gaps(full_answer)
    if len(found) < _SEVERAL_GAPS or _is_choice(short_answer):
        return []
    short = _comparable(short_answer)
    return [gap for gap in found if _comparable(gap) not in short]


def complete_short_answer(short_answer: str, full_answer: str) -> str:
    """Return a short answer that covers every gap of its full answer."""
    found = gaps(full_answer)
    if not short_answer.strip():
        # The key prints a dash where the gap takes no word.
        return GAP_SEPARATOR.join(found) if found else NO_WORD
    if missing_gaps(short_answer, full_answer):
        return GAP_SEPARATOR.join(found)
    return short_answer
