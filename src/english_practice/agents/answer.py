"""Answer Agent - evaluates, provides full answer, and extracts rule in one call."""

from pathlib import Path

from langsmith import traceable

from src.english_practice.agents.base import BaseAgent
from src.english_practice.models.agents import AnswerOutput
from src.english_practice.models.constants import PROMPT_ANSWER


class AnswerAgent(BaseAgent):
    """Agent for answer processing: evaluation, full answer, and rule extraction."""

    @traceable(name="process_answer")
    async def process_answer(
        self,
        image_path: Path,
        question_number: str,
        user_input: str,
        correct_answer: str,
        topic_name: str,
        rules_md: str,
        include_rule: bool = True,
    ) -> AnswerOutput:
        """Evaluate answer, provide full answer, and optionally extract grammar rule.

        Args:
            image_path: Path to the exercise image.
            question_number: The question number/ID.
            user_input: The user's answer.
            correct_answer: The correct answer.
            topic_name: The topic name for context.
            rules_md: The full rules markdown content.
            include_rule: Whether to include grammar rule extraction.

        Returns:
            AnswerOutput with is_correct, full_answer, and optional rule info.
        """
        prompt = self.render_agent_prompt(
            PROMPT_ANSWER,
            question_number=question_number,
            user_input=user_input,
            correct_answer=correct_answer,
            topic_name=topic_name,
            rules_md=rules_md,
            include_rule=include_rule,
        )

        return await self.invoke_structured(
            prompt=prompt,
            output_model=AnswerOutput,
            image_path=image_path,
        )
