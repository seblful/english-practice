"""Grading one answer: build the shared context, ask the decision model."""

from collections.abc import Sequence

from practice_core.grading import EvaluateAnswerInput, EvaluateAnswerOutput
from practice_core.models import Question, QuestionAnswer

from practice_app.decisions import DecisionClient

__all__ = ["Grader"]


class Grader:
    """Asks the configured decision model whether an answer is right."""

    def __init__(self, client: DecisionClient) -> None:
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
        context = EvaluateAnswerInput.for_question(
            question,
            user_input=user_input,
            answers=answers,
            topic_name=topic_name,
        )
        return await self._client.grade(context, image)
