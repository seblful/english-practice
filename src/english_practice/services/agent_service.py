"""Unified agent service for all LLM operations."""

import logging
from pathlib import Path

from src.english_practice.agents.answer import AnswerAgent
from src.english_practice.agents.assistant import AssistantAgent
from src.english_practice.models.agents import (
    AnswerOutput,
    AssistantOutput,
)
from src.english_practice.services.chat_history import ChatHistoryManager

logger = logging.getLogger(__name__)


class AgentService:
    """Unified service for all agent operations."""

    def __init__(self) -> None:
        """Initialize agent service with all agents."""
        self._answer_agent = AnswerAgent()
        self._assistant_agent = AssistantAgent()
        self._chat_history_manager = ChatHistoryManager()

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
        """Process user answer: evaluate, provide full answer, and optionally extract rule.

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
        return await self._answer_agent.process_answer(
            image_path=image_path,
            question_number=question_number,
            user_input=user_input,
            correct_answer=correct_answer,
            topic_name=topic_name,
            rules_md=rules_md,
            include_rule=include_rule,
        )

    async def assist(
        self,
        user_id: int,
        image_path: Path,
        question_number: str,
        user_input: str,
        topic_name: str,
    ) -> AssistantOutput:
        """Provide conversational assistance.

        Args:
            user_id: The user's ID for history tracking.
            image_path: Path to the exercise image.
            question_number: The question number/ID.
            user_input: The user's question or message.
            topic_name: The topic name for context.

        Returns:
            AssistantOutput with response.
        """
        return await self._assistant_agent.assist(
            user_id=user_id,
            image_path=image_path,
            question_number=question_number,
            user_input=user_input,
            topic_name=topic_name,
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
