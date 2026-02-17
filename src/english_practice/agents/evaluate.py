"""Evaluate Answer Agent - determines if user answer is correct."""

from pathlib import Path

from langsmith import traceable

from src.english_practice.agents.base import BaseAgent
from src.english_practice.models.agents import EvaluateAnswerOutput
from src.english_practice.agents.base import render_agent_prompt


class EvaluateAnswerAgent(BaseAgent):
    """Agent for evaluating if a user's answer is correct."""

    @traceable(name="evaluate_answer")
    def evaluate(
        self,
        image_path: Path,
        question_number: str,
        user_input: str,
        right_answer: str,
    ) -> EvaluateAnswerOutput:
        """Evaluate if the user's answer is correct.

        Args:
            image_path: Path to the exercise image.
            question_number: The question number/ID.
            user_input: The user's answer.
            right_answer: The correct answer.

        Returns:
            EvaluateAnswerOutput with is_correct boolean.
        """
        prompt = render_agent_prompt(
            "agent_evaluate.j2",
            question_number=question_number,
            user_input=user_input,
            right_answer=right_answer,
        )

        return self.invoke_structured(
            prompt=prompt,
            output_model=EvaluateAnswerOutput,
            image_path=image_path,
        )
