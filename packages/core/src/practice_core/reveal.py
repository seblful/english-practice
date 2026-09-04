"""What to show a student once their answer has been graded."""

from collections.abc import Sequence
from dataclasses import dataclass

from practice_core.grading import EvaluateAnswerOutput, answers_to_show
from practice_core.models import Question, QuestionAnswer

__all__ = ["Reveal", "reveal_for"]


def _plain(text: str) -> str:
    """Return text stripped of everything that is not a word."""
    words = text.replace("*", "").replace("_", "").split()
    return " ".join(words).strip(".").casefold()


def _adds_context(full: str, short: str) -> bool:
    """Return whether the book's whole sentence says more than the answer."""
    return _plain(full) != _plain(short)


@dataclass(frozen=True, slots=True)
class Reveal:
    """The book's answer to one question, and how much of it to show."""

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
        """Whether a verdict was reached."""
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
    """Decide what to reveal for one attempt."""
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
