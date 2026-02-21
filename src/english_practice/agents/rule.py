"""Get Rule Agent - extracts grammar rules from markdown."""

from pathlib import Path

from langsmith import traceable

from src.english_practice.agents.base import BaseAgent
from src.english_practice.models.agents import RuleOutput
from src.english_practice.models.constants import PROMPT_RULE


class GetRuleAgent(BaseAgent):
    """Agent for extracting grammar rules from rules markdown."""

    @traceable(name="get_rule")
    def get_rule(
        self,
        image_path: Path,
        question_number: str,
        rules_md: str,
        user_input: str,
        correct_answer: str,
        full_answer: str,
        topic_name: str,
    ) -> RuleOutput:
        """Extract the relevant grammar rule from the rules markdown.

        Args:
            image_path: Path to the exercise image.
            question_number: The question number/ID.
            rules_md: The full rules markdown content.
            user_input: The user's answer.
            correct_answer: The correct answer.
            full_answer: The full answer explanation from GetFullAnswerAgent.
            topic_name: The topic name for context.

        Returns:
            RuleOutput with the relevant rule.
        """
        prompt = self.render_agent_prompt(
            PROMPT_RULE,
            question_number=question_number,
            rules_md=rules_md,
            user_input=user_input,
            correct_answer=correct_answer,
            full_answer=full_answer,
            topic_name=topic_name,
        )

        return self.invoke_structured(
            prompt=prompt,
            output_model=RuleOutput,
            image_path=image_path,
        )
