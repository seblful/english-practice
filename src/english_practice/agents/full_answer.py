"""Get Full Answer Agent - provides detailed answer explanation."""

from pathlib import Path

from langsmith import traceable

from src.english_practice.agents.base import BaseAgent
from src.english_practice.models.agents import FullAnswerOutput
from src.english_practice.models.constants import PROMPT_FULL_ANSWER


class GetFullAnswerAgent(BaseAgent):
    """Agent for generating detailed answer explanations."""

    @traceable(name="get_full_answer")
    def get_full_answer(
        self,
        image_path: Path,
        question_number: str,
        correct_answer: str,
    ) -> FullAnswerOutput:
        """Generate a detailed explanation of the correct answer.

        Args:
            image_path: Path to the exercise image.
            question_number: The question number/ID.
            correct_answer: The correct answer.

        Returns:
            FullAnswerOutput with complete explanation.
        """
        prompt = self.render_agent_prompt(
            PROMPT_FULL_ANSWER,
            question_number=question_number,
            correct_answer=correct_answer,
        )

        return self.invoke_structured(
            prompt=prompt,
            output_model=FullAnswerOutput,
            image_path=image_path,
        )
