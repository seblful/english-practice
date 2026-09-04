"""The grading contract: what the model is asked, and how the answer is read.

Both front ends send the same prompt and read the reply the same way, which is
the point of this module: if the bot marked an answer right and the app marked
it wrong, the difference would be here.

They do not, however, reach a provider the same way. The bot gets a built model
back from LangChain's structured output; the app parses raw JSON. Neither path
can be trusted to sanitise the reply on its way past, and for a while only the
app did. So the rules live on :class:`EvaluateAnswerOutput` itself, as
validators: whichever path builds one, the same nonsense is dropped and the
same missing verdict is refused, because there is no way to build one without
crossing them.
"""

import json
from collections.abc import Mapping, Sequence
from typing import Any, Self

from pydantic import BaseModel, Field, ValidationError, field_validator

from practice_core.errors import GradingError
from practice_core.models import Question, QuestionAnswer

__all__ = [
    "EvaluateAnswerInput",
    "EvaluateAnswerOutput",
    "answers_to_show",
    "extract_json",
    "parse_evaluation",
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
    ) -> Self:
        """Build the prompt context for an attempt at one question.

        Four of the six fields are read straight off the question, so a caller
        that already holds one has no reason to take them apart -- and every
        caller does hold one. Spelling them out per front end is what had this
        six-field list written out four times between a Telegram handler and
        the prompt it ends in.

        Args:
            question: The question being answered.
            user_input: What the student typed.
            answers: The book's accepted answers, in order.
            topic_name: The topic, for context.

        Returns:
            The context to render the grading prompt with.
        """
        return cls(
            question_number=question.question_id,
            user_input=user_input,
            answers=list(answers),
            is_open_ended=question.is_open_ended,
            topic_name=topic_name,
            rule=question.rule,
        )


class EvaluateAnswerOutput(BaseModel):
    """The verdict the model returns.

    The validators below are the whole point of the type. A provider is free to
    reply with ``"answer_idx": [true, -1]`` or to leave the verdict out
    altogether, and both front ends have to react identically -- so the
    checking happens here, where neither can skip it, rather than in whichever
    parser one of them happens to use.
    """

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
        """Refuse anything but a real boolean.

        Pydantic would read ``1``, ``"true"`` or ``"yes"`` as ``True``. The
        verdict is the one field worth being strict about: a reply that says
        something else did not answer the question, and defaulting it either
        way would tell the student something the model never said.
        """
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

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Self:
        """Build a verdict from a decoded reply.

        Args:
            payload: The object the model replied with.

        Returns:
            The verdict, with any nonsense indexes dropped.

        Raises:
            GradingError: If the reply carries no usable ``is_correct``. A
                missing verdict cannot be guessed.
        """
        try:
            return cls.model_validate(dict(payload))
        except ValidationError as exc:
            # ``is_correct`` is the only field that can fail; the rest are emptied.
            raise GradingError(NO_VERDICT_MESSAGE) from exc


def answers_to_show(
    answers: Sequence[QuestionAnswer], matched_indexes: Sequence[int]
) -> tuple[QuestionAnswer, ...]:
    """Pick which expected answers to reveal.

    Args:
        answers: Every accepted answer, in book order.
        matched_indexes: Indexes the grader reported as matching.

    Returns:
        The matched answers, or the canonical first one when the grader matched
        nothing or reported an index that does not exist.
    """
    matched = tuple(
        answers[index] for index in matched_indexes if 0 <= index < len(answers)
    )
    return matched or tuple(answers[:1])


def extract_json(text: str) -> dict[str, Any]:
    """Return the JSON object a model replied with.

    Models are asked for a bare object and mostly comply, but a fenced block or
    a sentence of preamble is common enough that failing a grading over it
    would be a worse bug than this leniency.

    Args:
        text: The model's reply.

    Returns:
        The decoded object.

    Raises:
        GradingError: If the reply holds no JSON object.
    """
    candidate = text.strip()
    if candidate.startswith("```"):
        # Drop the opening fence with its optional language tag, then the close.
        candidate = candidate.split("\n", 1)[1] if "\n" in candidate else ""
        candidate = candidate.rsplit("```", 1)[0].strip()

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end > start:
        candidate = candidate[start : end + 1]

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise GradingError("The model's reply was not valid JSON.") from exc

    if not isinstance(parsed, dict):
        raise GradingError("The model replied with JSON, but not an object.")
    return parsed


def parse_evaluation(reply: str) -> EvaluateAnswerOutput:
    """Read a verdict out of a model's raw reply.

    This is the raw-text half of the contract, for a caller holding the reply
    as it arrived. A caller whose provider already built the model -- LangChain
    does -- gets the same checking from the validators on
    :class:`EvaluateAnswerOutput` and needs nothing from here.

    Args:
        reply: The reply text.

    Returns:
        The verdict, with any nonsense indexes dropped.

    Raises:
        GradingError: If the reply holds no JSON object, or carries no
            ``is_correct`` field.
    """
    return EvaluateAnswerOutput.from_payload(extract_json(reply))
