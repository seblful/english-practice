"""Extract full answers from exercise images using LLM."""

from collections.abc import Sequence
from pathlib import Path

from practice_runtime.agents import BaseAgent

from practice_extraction.models import (
    AnswersContext,
    AnswersQuestion,
    ExerciseAnswersOutput,
)


class AnswersAgent(BaseAgent):
    """Extract full answers from exercise images."""

    PROMPT_ANCHOR = "practice_extraction.agents"
    PROMPT_TEMPLATE = "answers.j2"

    async def extract_exercise(
        self,
        image_path: Path | None,
        questions: Sequence[AnswersQuestion],
        topic_name: str,
    ) -> ExerciseAnswersOutput:
        """Extract full answers for all questions in an exercise."""
        context = AnswersContext(questions=list(questions), topic_name=topic_name)
        prompt = self.render(context)

        return await self.invoke_structured(
            prompt=prompt,
            output_model=ExerciseAnswersOutput,
            image=image_path,
        )
