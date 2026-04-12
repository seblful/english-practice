"""Extract grammar rules from exercises using LLM."""

from pathlib import Path

from src.english_practice.agents.base import BaseAgent
from src.english_practice.models.agents import ExerciseRulesOutput
from src.english_practice.models.constants import PROMPT_RULE


class RuleExtractor(BaseAgent):
    """Extract grammar rules from exercises."""

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
        prompt = self.render_agent_prompt(
            PROMPT_RULE,
            questions=questions,
            rules_md=rules_md,
            topic_name=topic_name,
        )

        return await self.invoke_structured(
            prompt=prompt,
            output_model=ExerciseRulesOutput,
            image_path=image_path,
        )
