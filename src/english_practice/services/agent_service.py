"""Unified agent service for all LLM operations."""

import logging
from pathlib import Path

from src.english_practice.agents.evaluate import EvaluateAnswerAgent
from src.english_practice.agents.full_answer import GetFullAnswerAgent
from src.english_practice.agents.rule import GetRuleAgent
from src.english_practice.agents.assistant import AssistantAgent
from src.english_practice.models.agents import (
    AssistantOutput,
    EvaluateAnswerOutput,
    FullAnswerOutput,
    RuleOutput,
)
from src.english_practice.services.chat_history import ChatHistoryManager

logger = logging.getLogger(__name__)


class AgentService:
    """Unified service for all agent operations."""

    def __init__(self) -> None:
        """Initialize agent service with all agents."""
        self._evaluate_agent = EvaluateAnswerAgent()
        self._full_answer_agent = GetFullAnswerAgent()
        self._rule_agent = GetRuleAgent()
        self._assistant_agent = AssistantAgent()
        self._chat_history_manager = ChatHistoryManager()

    def evaluate_answer(
        self,
        image_path: Path,
        question_number: str,
        user_input: str,
        right_answer: str,
    ) -> EvaluateAnswerOutput:
        """Evaluate if the user's answer is correct.

        Args:
            image_path: Path to the exercise image.
            question_number: The question number/ID.
            user_input: The user's answer.
            right_answer: The correct answer.

        Returns:
            EvaluateAnswerOutput with is_correct boolean.
        """
        return self._evaluate_agent.evaluate(
            image_path=image_path,
            question_number=question_number,
            user_input=user_input,
            right_answer=right_answer,
        )

    def get_full_answer(
        self,
        image_path: Path,
        question_number: str,
        right_answer: str,
    ) -> FullAnswerOutput:
        """Get detailed explanation of the correct answer.

        Args:
            image_path: Path to the exercise image.
            question_number: The question number/ID.
            right_answer: The correct answer.

        Returns:
            FullAnswerOutput with sentence and explanation.
        """
        return self._full_answer_agent.get_full_answer(
            image_path=image_path,
            question_number=question_number,
            right_answer=right_answer,
        )

    def get_rule(
        self,
        rules_md: str,
        user_input: str,
        right_answer: str,
        full_answer: str,
    ) -> RuleOutput:
        """Extract grammar rule from rules markdown.

        Args:
            rules_md: The full rules markdown content.
            user_input: The user's answer.
            right_answer: The correct answer.
            full_answer: The full answer explanation.

        Returns:
            RuleOutput with rule and explanation.
        """
        return self._rule_agent.get_rule(
            rules_md=rules_md,
            user_input=user_input,
            right_answer=right_answer,
            full_answer=full_answer,
        )

    def assist(
        self,
        user_id: int,
        image_path: Path,
        question_number: str,
        user_input: str,
    ) -> AssistantOutput:
        """Provide conversational assistance.

        Args:
            user_id: The user's ID for history tracking.
            image_path: Path to the exercise image.
            question_number: The question number/ID.
            user_input: The user's question or message.

        Returns:
            AssistantOutput with response.
        """
        return self._assistant_agent.assist(
            user_id=user_id,
            image_path=image_path,
            question_number=question_number,
            user_input=user_input,
            chat_history_manager=self._chat_history_manager,
        )

    def on_new_image(self, user_id: int, new_image_path: Path) -> None:
        """Handle new image - clear chat history for previous images.

        Args:
            user_id: The user's ID.
            new_image_path: Path to the new exercise image.
        """
        self._assistant_agent.on_new_image(
            user_id, new_image_path, self._chat_history_manager
        )

    def clear_all_history(self, user_id: int) -> None:
        """Clear all chat history for a user.

        Args:
            user_id: The user's ID.
        """
        self._chat_history_manager.clear_user_history(user_id)
