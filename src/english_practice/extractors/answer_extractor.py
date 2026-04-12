"""Extract full answers from exercise images using LLM."""

from pathlib import Path

from src.english_practice.agents.base import BaseAgent
from src.english_practice.models.agents import ExerciseAnswersOutput
from src.english_practice.models.constants import PROMPT_FULL_ANSWER


class AnswerExtractor(BaseAgent):
    """Extract full answers from exercise images."""

    async def extract_exercise(
        self,
        image_path: Path,
        questions: list[dict],
        topic_name: str,
    ) -> ExerciseAnswersOutput:
        """Extract full answers for all questions in an exercise.

        Args:
            image_path: Path to the exercise image.
            questions: List of dicts with question_id and short_answers.
            topic_name: The topic name for context.

        Returns:
            ExerciseAnswersOutput with all question answers.
        """
        prompt = self.render_agent_prompt(
            PROMPT_FULL_ANSWER,
            questions=questions,
            topic_name=topic_name,
        )

        return await self.invoke_structured(
            prompt=prompt,
            output_model=ExerciseAnswersOutput,
            image_path=image_path,
        )
