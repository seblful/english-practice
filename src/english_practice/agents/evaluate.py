"""Evaluate agent: decides whether the student's answer is correct."""

from collections.abc import Sequence

from english_practice.agents.base import BaseAgent
from english_practice.agents.tracing import traced
from english_practice.models.agents import EvaluateAnswerInput, EvaluateAnswerOutput
from english_practice.models.book import QuestionAnswer


class EvaluateAnswerAgent(BaseAgent):
    """Grades a student's answer against the book's expected answers."""

    PROMPT_TEMPLATE = "evaluate.j2"

    @traced(name="evaluate_answer")
    async def evaluate(
        self,
        *,
        image_data: bytes | None,
        question_number: str,
        user_input: str,
        answers: Sequence[QuestionAnswer],
        is_open_ended: bool,
        topic_name: str,
        rule: str | None = None,
    ) -> EvaluateAnswerOutput:
        """Grade the student's answer.

        Args:
            image_data: Raw exercise image bytes, if the exercise has one.
            question_number: The question number/ID.
            user_input: The student's answer.
            answers: Expected answers in display order; ``answer_idx`` in the
                result indexes into this sequence.
            is_open_ended: Whether the question allows free-form responses.
            topic_name: The topic name, for context.
            rule: The grammar rule for this question, when known.

        Returns:
            Whether the answer is correct, and which expected answers matched.

        Raises:
            AgentError: If the LLM call fails or cannot be parsed.
        """
        context = EvaluateAnswerInput(
            question_number=question_number,
            user_input=user_input,
            answers=list(answers),
            is_open_ended=is_open_ended,
            topic_name=topic_name,
            rule=rule,
        )

        return await self.invoke_structured(
            prompt=self.render(context),
            output_model=EvaluateAnswerOutput,
            image_data=image_data,
        )
