"""Grading one answer: render the shared prompt, call the model, read the verdict."""

from collections.abc import Sequence

from practice_core.grading import (
    EvaluateAnswerInput,
    EvaluateAnswerOutput,
    parse_evaluation,
)
from practice_core.models import Question, QuestionAnswer
from practice_core.prompts import render_evaluate_prompt

from practice_app.llm import LLMClient

__all__ = ["Grader"]


class Grader:
    """Asks the configured model whether an answer is right."""

    def __init__(self, client: LLMClient) -> None:
        """Initialize the grader."""
        self._client = client

    async def grade(
        self,
        *,
        question: Question,
        user_input: str,
        answers: Sequence[QuestionAnswer],
        topic_name: str,
        image: bytes | None = None,
    ) -> EvaluateAnswerOutput:
        """Grade one answer."""
        prompt = render_evaluate_prompt(
            EvaluateAnswerInput.for_question(
                question,
                user_input=user_input,
                answers=answers,
                topic_name=topic_name,
            )
        )
        return parse_evaluation(await self._client.complete(prompt, image))
