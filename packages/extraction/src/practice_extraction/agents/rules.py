"""Extract grammar rules from exercises using LLM."""

from collections.abc import Sequence
from pathlib import Path

from practice_runtime.agents import BaseAgent

from practice_extraction.models import (
    ExerciseRulesOutput,
    RulesContext,
    RulesQuestion,
)


class RulesAgent(BaseAgent):
    """Extract grammar rules from exercises."""

    PROMPT_ANCHOR = "practice_extraction.agents"
    PROMPT_TEMPLATE = "rules.j2"

    async def extract_exercise(
        self,
        image_path: Path | None,
        questions: Sequence[RulesQuestion],
        rules_md: str,
        topic_name: str,
    ) -> ExerciseRulesOutput:
        """Extract grammar rules for all questions in an exercise.

        Args:
            image_path: Path to the exercise image, if one exists.
            questions: The exercise's questions, with the answers already extracted.
            rules_md: The grammar rules markdown.
            topic_name: The topic name for context.

        Returns:
            ExerciseRulesOutput with all question rules.
        """
        context = RulesContext(
            questions=list(questions),
            rules_md=rules_md,
            topic_name=topic_name,
        )
        prompt = self.render(context)

        image_data = (
            image_path.read_bytes()
            if image_path is not None and image_path.exists()
            else None
        )

        return await self.invoke_structured(
            prompt=prompt,
            output_model=ExerciseRulesOutput,
            image_data=image_data,
        )
