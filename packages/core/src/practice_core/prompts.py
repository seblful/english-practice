"""The text a grading request carries, shared by every front end."""

import json
import re
from typing import Final, Self

from pydantic import BaseModel

from practice_core.grading import EvaluateAnswerInput
from practice_core.templates import render_packaged_template

__all__ = [
    "DECISION_TEMPLATE",
    "PROMPT_ANCHOR",
    "DecisionPrompt",
    "PromptAnswer",
    "book_text",
    "render_decision_input",
    "student_text",
]

PROMPT_ANCHOR = "practice_core"
DECISION_TEMPLATE = "decision.j2"

# The book bolds the words a student writes, so the bold is where the gaps are.
_GAP: Final = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
# Phones type curly apostrophes and the book prints them; neither is grammar.
_APOSTROPHES: Final = str.maketrans(
    {"\N{RIGHT SINGLE QUOTATION MARK}": "'", "\N{LEFT SINGLE QUOTATION MARK}": "'"}
)


def student_text(text: str) -> str:
    """Return what a student typed with plain apostrophes and no stray spaces."""
    return " ".join(text.translate(_APOSTROPHES).split())


def book_text(text: str) -> str:
    """Return book text with its gaps in square brackets and plain apostrophes."""
    return _GAP.sub(r"[\1]", text).replace("**", "").translate(_APOSTROPHES)


class PromptAnswer(BaseModel):
    """One accepted answer, as the grader reads it."""

    short: str
    full: str


class DecisionPrompt(BaseModel):
    """What the grading template prints, already in the grader's notation."""

    question_number: str
    unit_title: str | None
    topic_name: str
    rule: str | None
    free_form: bool
    answers: list[PromptAnswer]
    student_answer: str

    @classmethod
    def from_context(cls, context: EvaluateAnswerInput) -> Self:
        """Build the template's view of one attempt."""
        free_form = context.is_open_ended or not context.answers
        return cls(
            question_number=context.question_number,
            unit_title=context.unit_title,
            topic_name=context.topic_name,
            # The rule's bold is emphasis, not gaps, so it is only dropped.
            rule=context.rule.replace("**", "") if context.rule else None,
            free_form=free_form,
            answers=[]
            if free_form
            else [
                PromptAnswer(
                    short=book_text(answer.short_answer),
                    full=book_text(answer.full_answer),
                )
                for answer in context.answers
            ],
            # Quoted as JSON so a typed quote mark cannot close the string early.
            student_answer=json.dumps(
                student_text(context.user_input), ensure_ascii=False
            ),
        )


def render_decision_input(context: EvaluateAnswerInput) -> str:
    """Render the text that sits beside the exercise image in a grading request."""
    return render_packaged_template(
        PROMPT_ANCHOR, DECISION_TEMPLATE, DecisionPrompt.from_context(context)
    )
