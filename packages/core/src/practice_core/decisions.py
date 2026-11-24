"""Grading through a decision model: the questions asked, and the verdict read back."""

import base64
from collections.abc import Mapping
from typing import Any, Final

from practice_core.errors import GradingError
from practice_core.grading import (
    NO_VERDICT_MESSAGE,
    EvaluateAnswerInput,
    EvaluateAnswerOutput,
)
from practice_core.images import data_uri, image_media_type
from practice_core.prompts import book_text, render_decision_input
from practice_core.providers import Provider

__all__ = [
    "VERDICT_KEY",
    "decision_request",
    "match_key",
    "read_decision",
]


VERDICT_KEY: Final = "is_correct"
_MATCH_PREFIX: Final = "matches_"

# A yes/no answer is a calibrated P(yes); above a coin toss reads as yes.
_YES: Final = 0.5

_EQUIVALENCE: Final = (
    "Contractions and their expanded forms are identical (I'm = I am, "
    "can't = cannot, he'd = he would or he had). A slash in an accepted answer "
    "separates alternatives, and matching one side is enough. Ignore "
    "capitalization, trailing punctuation and extra spaces."
)

# How the book writes an answer, which a literal match would get wrong.
_FORMS: Final = (
    "An ellipsis (…) in a short answer separates the words for different gaps: "
    "the student must fill every gap, and may separate them with commas, dots or "
    "spaces, or write the whole sentence. A single letter as the short answer is "
    "a choice from a list in the exercise, so the letter or the text of that "
    "option both match. A dash (—) means the gap takes no word, so a dash, "
    '"nothing", or the sentence with no word there all match.'
)

_TYPOS: Final = (
    "A minor spelling mistake in a word unrelated to the target grammar is still "
    "correct."
)

_CLOSED_VERDICT: Final = (
    "Is the student's answer correct? It is correct when it matches at least one "
    "accepted answer: its short form, its full sentence, or the bracketed gaps of "
    "that sentence. "
    + _FORMS
    + " "
    + _EQUIVALENCE
    + " "
    + _TYPOS
    + " Extra words that change the grammatical structure or the meaning make it "
    "incorrect."
)

_OPEN_VERDICT: Final = (
    "Is the student's answer correct? The question is open-ended, so do not match "
    "it against a fixed answer. It is correct when it uses the target grammar of "
    "the topic and rule properly and makes sense for this question in the "
    "exercise picture. Forgive minor spelling mistakes when the target grammar is "
    "correct."
)

_ACCEPTABLE: Final = "The student's answer is acceptable."
_UNACCEPTABLE: Final = "The student's answer is wrong or answers something else."

# The same two descriptions, under the key names each provider documents.
_VERDICT_CRITERIA: Final = {
    Provider.OPENROUTER: {"true": _ACCEPTABLE, "false": _UNACCEPTABLE},
    Provider.GEMINI: {
        "true_description": _ACCEPTABLE,
        "false_description": _UNACCEPTABLE,
    },
}

_REFUSED: Final = "The grader declined to judge this answer."


def match_key(index: int) -> str:
    """Return the question key that asks whether accepted answer ``index`` matched."""
    return f"{_MATCH_PREFIX}{index}"


def _free_form(context: EvaluateAnswerInput) -> bool:
    """Whether there is no list to match: open-ended, or the book records none."""
    return context.is_open_ended or not context.answers


def _questions(
    context: EvaluateAnswerInput, provider: Provider
) -> dict[str, dict[str, Any]]:
    """Return the verdict question, plus one match question per accepted answer."""
    free_form = _free_form(context)
    questions: dict[str, dict[str, Any]] = {
        VERDICT_KEY: {
            "type": "noul",
            "instructions": _OPEN_VERDICT if free_form else _CLOSED_VERDICT,
            "criteria": _VERDICT_CRITERIA[provider],
        }
    }
    if free_form:
        return questions

    for index, answer in enumerate(context.answers):
        questions[match_key(index)] = {
            "type": "noul",
            "instructions": (
                f"Does the student's answer match accepted answer {index}: short "
                f'"{book_text(answer.short_answer)}" or full '
                f'"{book_text(answer.full_answer)}"? {_FORMS} {_EQUIVALENCE} {_TYPOS}'
            ),
        }
    return questions


def decision_request(
    context: EvaluateAnswerInput,
    *,
    provider: Provider,
    model: str,
    image: bytes | None = None,
) -> dict[str, Any]:
    """Return the body of a decision request that grades one answer."""
    text = render_decision_input(context)
    questions = _questions(context, provider)

    if provider is Provider.OPENROUTER:
        # OpenRouter's `state` takes text as plain strings, images as data URLs.
        state: list[Any] = []
        if image:
            state.append({"type": "image_url", "image_url": {"url": data_uri(image)}})
        state.append(text)
        return {"model": model, "state": state, "questions": questions}

    blocks: list[dict[str, Any]] = []
    if image:
        blocks.append(
            {
                "type": "image",
                "data": base64.b64encode(image).decode("ascii"),
                "mime_type": image_media_type(image),
            }
        )
    blocks.append({"type": "text", "text": text})
    return {"model": model, "input": blocks, "questions": questions}


def _probability(answer: object) -> float | None:
    """Return the P(yes) of one yes/no answer, or ``None`` when there is none."""
    if not isinstance(answer, Mapping):
        return None
    value = answer.get("noul")
    # bool is an int subclass, and `true` is not a probability.
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _block_reason(feedback: object) -> str:
    """Return why the API refused the input, or empty when it did not."""
    if not isinstance(feedback, Mapping):
        return ""
    reason = feedback.get("block_reason")
    # Google's enums carry an UNSPECIFIED zero value that blocks nothing.
    if not isinstance(reason, str) or "unspecified" in reason.lower():
        return ""
    return reason


def read_decision(
    payload: object, context: EvaluateAnswerInput
) -> EvaluateAnswerOutput:
    """Read a verdict out of either provider's reply to :func:`decision_request`."""
    if not isinstance(payload, Mapping):
        raise GradingError(NO_VERDICT_MESSAGE)

    reason = _block_reason(payload.get("prompt_feedback"))
    if reason:
        raise GradingError(f"The grader refused this exercise ({reason}).")

    answers = payload.get("answers")
    if not isinstance(answers, Mapping):
        raise GradingError(NO_VERDICT_MESSAGE)

    answer = answers.get(VERDICT_KEY)
    if isinstance(answer, Mapping) and answer.get("type") == "refusal":
        raise GradingError(_REFUSED)
    verdict = _probability(answer)
    if verdict is None:
        raise GradingError(NO_VERDICT_MESSAGE)

    is_correct = verdict > _YES
    # A match is only shown as what the student got right, so a wrong answer has none.
    chances = (
        {}
        if _free_form(context) or not is_correct
        else {
            index: chance
            for index in range(len(context.answers))
            if (chance := _probability(answers.get(match_key(index)))) is not None
        }
    )
    matched = [index for index, chance in chances.items() if chance > _YES]
    if not matched and chances:
        # The verdict is yes, so the likeliest answer beats the first one shown.
        matched = [max(chances, key=chances.__getitem__)]
    return EvaluateAnswerOutput(is_correct=is_correct, answer_idx=matched)
