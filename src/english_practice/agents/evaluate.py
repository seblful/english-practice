"""Evaluate Answer Agent - determines if user answer is correct."""

from langsmith import traceable

from src.english_practice.agents.base import BaseAgent
from src.english_practice.models.agents import EvaluateAnswerInput, EvaluateAnswerOutput


class EvaluateAnswerAgent(BaseAgent):
    """Agent for evaluating if a user's answer is correct."""

    PROMPT_TEMPLATE = "evaluate.j2"

    @traceable(name="evaluate_answer")
    async def evaluate(
        self,
        image_data: bytes,
        question_number: str,
        user_input: str,
        short_answers: list[str],
        full_answers: list[str],
        is_open_ended: bool,
        topic_name: str,
        rule: str | None = None,
    ) -> EvaluateAnswerOutput:
        """Evaluate if the user's answer is correct.

        Args:
            image_data: Raw exercise image bytes.
            question_number: The question number/ID.
            user_input: The user's answer.
            short_answers: All short answer variants.
            full_answers: All full answer variants (parallel to short_answers).
            is_open_ended: Whether the question allows free-form responses.
            topic_name: The topic name for context.
            rule: Optional grammar rule for this question.

        Returns:
            EvaluateAnswerOutput with is_correct and answer_idx.
        """
        context = EvaluateAnswerInput(
            question_number=question_number,
            user_input=user_input,
            short_answers=short_answers,
            full_answers=full_answers,
            is_open_ended=is_open_ended,
            topic_name=topic_name,
            rule=rule,
        )
        prompt = self.render(context)

        return await self.invoke_structured(
            prompt=prompt,
            output_model=EvaluateAnswerOutput,
            image_data=image_data,
        )
