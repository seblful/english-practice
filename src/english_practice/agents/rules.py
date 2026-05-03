"""Extract grammar rules from exercises using LLM."""

from pathlib import Path

from src.english_practice.agents.base import BaseAgent
from src.english_practice.models.agents import ExerciseRulesOutput, RulesContext


class RulesAgent(BaseAgent):
    """Extract grammar rules from exercises."""

    PROMPT_TEMPLATE = "rules.j2"

    async def extract_exercise(
        self,
        image_path: Path,
        questions: list[dict],
        rules_md: str,
        topic_name: str,
    ) -> ExerciseRulesOutput:
        """Extract grammar rules for all questions in an exercise.

        Args:
            image_path: Path to the exercise image.
            questions: List of dicts with question_id, short_answer, full_answer.
            rules_md: The grammar rules markdown.
            topic_name: The topic name for context.

        Returns:
            ExerciseRulesOutput with all question rules.
        """
        context = RulesContext(
            questions=questions,
            rules_md=rules_md,
            topic_name=topic_name,
        )
        prompt = self.render(context)

        image_data = image_path.read_bytes() if image_path.exists() else None

        return await self.invoke_structured(
            prompt=prompt,
            output_model=ExerciseRulesOutput,
            image_data=image_data,
        )
