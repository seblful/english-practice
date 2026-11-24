"""The grading contract: what an attempt carries, and what a verdict holds."""

from collections.abc import Sequence
from typing import Self

from pydantic import BaseModel, Field, field_validator

from practice_core.models import Question, QuestionAnswer

__all__ = [
    "NO_VERDICT_MESSAGE",
    "EvaluateAnswerInput",
    "EvaluateAnswerOutput",
    "answers_to_show",
]

# Shown to the student, so it says what happened rather than naming a field.
NO_VERDICT_MESSAGE = "The model did not say whether the answer was correct."


class EvaluateAnswerInput(BaseModel):
    """Everything the grading prompt needs about one attempt."""

    question_number: str = Field(description="Question number as printed")
    user_input: str = Field(description="What the student typed")
    answers: list[QuestionAnswer] = Field(
        default_factory=list, description="Accepted answers, in book order"
    )
    is_open_ended: bool = Field(
        default=False, description="Whether free-form answers are accepted"
    )
    unit_title: str | None = Field(
        default=None, description="Unit title, naming the grammar it practises"
    )
    topic_name: str = Field(description="Topic, for context")
    rule: str | None = Field(default=None, description="Grammar rule, when known")

    @classmethod
    def for_question(
        cls,
        question: Question,
        *,
        user_input: str,
        answers: Sequence[QuestionAnswer],
        topic_name: str,
        unit_title: str | None,
    ) -> Self:
        """Build the prompt context for an attempt at one question."""
        return cls(
            question_number=question.question_id,
            user_input=user_input,
            answers=list(answers),
            is_open_ended=question.is_open_ended,
            unit_title=unit_title,
            topic_name=topic_name,
            rule=question.rule,
        )


class EvaluateAnswerOutput(BaseModel):
    """The verdict the model returns."""

    is_correct: bool = Field(
        description="Whether the user's answer is correct (true) or incorrect (false)"
    )
    answer_idx: list[int] = Field(
        default_factory=list,
        description=(
            "List of indexes of matched answers in the answers array. "
            "Empty list for open-ended or no match."
        ),
    )

    @field_validator("is_correct", mode="before")
    @classmethod
    def _reject_a_guessed_verdict(cls, value: object) -> object:
        """Refuse anything but a real boolean."""
        if not isinstance(value, bool):
            raise ValueError(NO_VERDICT_MESSAGE)
        return value

    @field_validator("answer_idx", mode="before")
    @classmethod
    def _drop_indexes_that_mean_nothing(cls, value: object) -> object:
        """Keep only the non-negative integers a model actually reported."""
        if not isinstance(value, list):
            # A scalar, a string or ``null`` means the field was ignored.
            return []
        return [
            index
            for index in value
            # bool is an int subclass, and `true` in that array means nothing.
            if isinstance(index, int) and not isinstance(index, bool) and index >= 0
        ]


def answers_to_show(
    answers: Sequence[QuestionAnswer], matched_indexes: Sequence[int]
) -> tuple[QuestionAnswer, ...]:
    """Pick which expected answers to reveal."""
    matched = tuple(
        answers[index] for index in matched_indexes if 0 <= index < len(answers)
    )
    return matched or tuple(answers[:1])
