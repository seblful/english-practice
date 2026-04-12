"""Evaluate Answer Agent - determines if user answer is correct."""

from pathlib import Path

from langsmith import traceable

from src.english_practice.agents.base import BaseAgent
from src.english_practice.models.agents import EvaluateAnswerInput, EvaluateAnswerOutput


class EvaluateAnswerAgent(BaseAgent):
    """Agent for evaluating if a user's answer is correct."""

    PROMPT_TEMPLATE = "agent_evaluate.j2"

    @traceable(name="evaluate_answer")
    async def evaluate(
        self,
        image_path: Path,
        question_number: str,
        user_input: str,
        correct_answer: str,
        full_answer: str,
        topic_name: str,
    ) -> EvaluateAnswerOutput:
        """Evaluate if the user's answer is correct.

        Args:
            image_path: Path to the exercise image.
            question_number: The question number/ID.
            user_input: The user's answer.
            correct_answer: The correct answer.
            full_answer: The full answer explanation to help evaluate.
            topic_name: The topic name for context.

        Returns:
            EvaluateAnswerOutput with is_correct boolean and full_answer.
        """
        context = EvaluateAnswerInput(
            question_number=question_number,
            user_input=user_input,
            correct_answer=correct_answer,
            full_answer=full_answer,
            topic_name=topic_name,
        )
        prompt = self.render(context)

        return await self.invoke_structured(
            prompt=prompt,
            output_model=EvaluateAnswerOutput,
            image_path=image_path,
        )
