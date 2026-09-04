"""What to show a student once their answer has been graded.

The two front ends render a reveal very differently -- a stack of Telegram
messages, a Material sheet over the question -- but *what* belongs in it is a
domain decision rather than a rendering one: which of the book's answers,
whether the whole sentence adds anything to the short form, whether the rule
follows, and whether an open-ended question has an answer to print at all.

Written twice, those rules drifted. The bot printed the book's full sentence
under every answer, including the ones the app had already decided were
redundant, and both front ends fell back to the first stored answer for an
open-ended question -- which the grading prompt forbids, because handing over
a phrasing invites matching it. This module decides once, and each front end
renders what it is given.

What a failed grading *costs* is deliberately not decided here. The bot's
endless stream can offer another attempt where the app's fixed-length lesson
cannot, so both read :attr:`Reveal.was_graded` and apply their own policy to
it -- one field, rather than a flag each invented for itself.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from practice_core.grading import EvaluateAnswerOutput, answers_to_show
from practice_core.models import Question, QuestionAnswer

__all__ = ["Reveal", "reveal_for"]


def _plain(text: str) -> str:
    """Return text stripped of everything that is not a word.

    Args:
        text: Markdown from the book.

    Returns:
        The words alone: no emphasis, no end stop, one space between them, and
        case folded, so two spellings of the same answer compare equal.
    """
    words = text.replace("*", "").replace("_", "").split()
    return " ".join(words).strip(".").casefold()


def _adds_context(full: str, short: str) -> bool:
    """Return whether the book's whole sentence says more than the answer.

    A question that asks for a complete sentence prints the same words in both
    of the book's fields, and showing them one under the other reads as a
    rendering bug rather than as a correction.

    Args:
        full: The full answers, joined.
        short: The short answers, joined.

    Returns:
        Whether the sentence is worth printing under the answer.
    """
    return _plain(full) != _plain(short)


@dataclass(frozen=True, slots=True)
class Reveal:
    """The book's answer to one question, and how much of it to show.

    The text itself is not built here: the bot joins the full sentences with a
    single newline inside a preformatted block and the app with a blank line,
    because a markdown renderer reads a single newline as a soft wrap. So this
    carries the answers and the decisions, and
    :mod:`practice_core.feedback` turns them into strings.

    Nor is the praise. :func:`practice_core.feedback.verdict_phrase` picks one
    at random, so a value computed here would reshuffle itself on every
    repaint; each front end calls it once, when the verdict arrives.
    """

    answers: tuple[QuestionAnswer, ...]
    """The answers to print, in book order. Empty for an open-ended question."""

    is_correct: bool | None
    """The verdict, or ``None`` when the answer was never graded."""

    show_full_answer: bool
    """Whether the book's whole sentence says more than the short answer."""

    rule: str | None
    """The grammar rule to quote, or ``None`` when there is none to show."""

    unit_reference: str
    """The unit and section the question came from, for example ``"12B"``."""

    @property
    def was_graded(self) -> bool:
        """Whether a verdict was reached.

        ``False`` covers both a student who asked for the answer and a grading
        that failed. What that costs is the front end's to decide.
        """
        return self.is_correct is not None

    @property
    def has_answer(self) -> bool:
        """Whether the book prints an answer for this question."""
        return bool(self.answers)


def reveal_for(
    question: Question,
    *,
    answers: Sequence[QuestionAnswer],
    unit_number: int,
    evaluation: EvaluateAnswerOutput | None,
    show_rule: bool = True,
) -> Reveal:
    """Decide what to reveal for one attempt.

    Args:
        question: The question that was answered.
        answers: Every accepted answer the book stores, in order.
        unit_number: The unit the question came from, as printed.
        evaluation: The verdict, or ``None`` when the answer was revealed
            without one -- the student asked, or grading failed.
        show_rule: Whether the student has rules turned on.

    Returns:
        The answers to print and the decisions around them.
    """
    if question.is_open_ended:
        # The prompt forbids an answer here: a stored one invites matching it.
        shown: tuple[QuestionAnswer, ...] = ()
    elif evaluation is not None:
        shown = answers_to_show(answers, evaluation.answer_idx)
    else:
        # Nothing was graded, so nothing was matched.
        shown = tuple(answers[:1])

    is_correct = evaluation.is_correct if evaluation is not None else None

    show_full = False
    if shown and not is_correct:
        # Confirmation should be quick to dismiss.
        short = ", ".join(answer.short_answer for answer in shown)
        full = "\n".join(answer.full_answer for answer in shown)
        show_full = _adds_context(full, short)

    return Reveal(
        answers=shown,
        is_correct=is_correct,
        show_full_answer=show_full,
        rule=question.rule if show_rule and question.has_rule else None,
        unit_reference=f"{unit_number}{question.section_letter or ''}",
    )
