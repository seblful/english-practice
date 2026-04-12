"""Extract full answers from exercise images using LLM."""

from pathlib import Path

from src.english_practice.agents.base import BaseAgent
from src.english_practice.models.agents import AnswersContext, ExerciseAnswersOutput


class AnswersAgent(BaseAgent):
    """Extract full answers from exercise images."""

    PROMPT_TEMPLATE = "answers.j2"

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
        context = AnswersContext(questions=questions, topic_name=topic_name)
        prompt = self.render(context)

        return await self.invoke_structured(
            prompt=prompt,
            output_model=ExerciseAnswersOutput,
            image_path=image_path,
        )
