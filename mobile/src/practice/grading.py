"""Grading one answer: render the shared prompt, call the model, read the verdict.

Every decision about *how* an answer is graded belongs to
:mod:`practice_core` — the prompt, the rules inside it, and how the reply is
parsed — so the app and the bot cannot drift into marking the same answer
differently. What is left here is the call itself.
"""

from collections.abc import Sequence

from practice_core.grading import (
    EvaluateAnswerInput,
    EvaluateAnswerOutput,
    parse_evaluation,
)
from practice_core.models import Question, QuestionAnswer
from practice_core.prompts import render_evaluate_prompt

from practice.llm import LLMClient

__all__ = ["Grader"]


class Grader:
    """Asks the configured model whether an answer is right."""

    def __init__(self, client: LLMClient) -> None:
        """Initialize the grader.

        Args:
            client: The provider client to grade through.
        """
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
        """Grade one answer.

        Args:
            question: The question being answered.
            user_input: What the student typed.
            answers: The book's accepted answers, in order.
            topic_name: The topic, for context.
            image: The exercise image, when the exercise has one.

        Returns:
            The verdict, and which expected answers it matched.

        Raises:
            ConfigurationError: If the app is not configured yet.
            GradingError: If the verdict cannot be read back.
            ProviderError: If the call itself fails.
        """
        prompt = render_evaluate_prompt(
            EvaluateAnswerInput(
                question_number=question.question_id,
                user_input=user_input,
                answers=list(answers),
                is_open_ended=question.is_open_ended,
                topic_name=topic_name,
                rule=question.rule,
            )
        )
        return parse_evaluation(await self._client.complete(prompt, image))
