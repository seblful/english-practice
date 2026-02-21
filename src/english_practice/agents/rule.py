"""Get Rule Agent - extracts grammar rules from markdown."""

from langsmith import traceable

from src.english_practice.agents.base import BaseAgent
from src.english_practice.models.agents import RuleOutput
from src.english_practice.models.constants import PROMPT_RULE


class GetRuleAgent(BaseAgent):
    """Agent for extracting grammar rules from rules markdown."""

    @traceable(name="get_rule")
    def get_rule(
        self,
        rules_md: str,
        user_input: str,
        right_answer: str,
        full_answer: str,
    ) -> RuleOutput:
        """Extract the relevant grammar rule from the rules markdown.

        Args:
            rules_md: The full rules markdown content.
            user_input: The user's answer.
            right_answer: The correct answer.
            full_answer: The full answer explanation from GetFullAnswerAgent.

        Returns:
            RuleOutput with rule and explanation.
        """
        prompt = self.render_agent_prompt(
            PROMPT_RULE,
            rules_md=rules_md,
            user_input=user_input,
            right_answer=right_answer,
            full_answer=full_answer,
        )

        # No image needed for rule extraction
        return self.invoke_structured(
            prompt=prompt,
            output_model=RuleOutput,
            image_path=None,
        )
