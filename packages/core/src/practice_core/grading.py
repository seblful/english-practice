"""The grading contract: what the model is asked, and how the answer is read.

Both front ends send the same prompt and read the reply the same way, which is
the point of this module: if the bot marked an answer right and the app marked
it wrong, the difference would be here.

The bot reaches its provider through LangChain's structured output and the app
parses raw JSON, so both paths end at :func:`parse_evaluation` — one with a
model already built, one with text to read first.
"""

import json
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field

from practice_core.errors import GradingError
from practice_core.models import QuestionAnswer

__all__ = [
    "EvaluateAnswerInput",
    "EvaluateAnswerOutput",
    "answers_to_show",
    "extract_json",
    "parse_evaluation",
]


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

    Args:
        reply: The reply text.

    Returns:
        The verdict, with any nonsense indexes dropped.

    Raises:
        GradingError: If the reply carries no ``is_correct`` field. A missing
            verdict cannot be guessed: defaulting it either way would tell the
            student something the model never said.
    """
    payload = extract_json(reply)

    verdict = payload.get("is_correct")
    if not isinstance(verdict, bool):
        raise GradingError("The model did not say whether the answer was correct.")

    raw = payload.get("answer_idx")
    indexes = raw if isinstance(raw, list) else []
    return EvaluateAnswerOutput(
        is_correct=verdict,
        answer_idx=[
            index
            for index in indexes
            # bool is an int subclass, and `true` in that array means nothing.
            if isinstance(index, int) and not isinstance(index, bool) and index >= 0
        ],
    )
