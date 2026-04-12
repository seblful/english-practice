"""Unified agent service for all LLM operations."""

import logging
from pathlib import Path

from src.english_practice.agents.evaluate import EvaluateAnswerAgent
from src.english_practice.agents.assistant import AssistantAgent
from src.english_practice.models.agents import (
    AssistantOutput,
    EvaluateAnswerOutput,
)
from src.english_practice.services.chat_history import ChatHistoryManager

logger = logging.getLogger(__name__)


class AgentService:
    """Unified service for all agent operations."""

    def __init__(self) -> None:
        """Initialize agent service with all agents."""
        self._evaluate_agent = EvaluateAnswerAgent()
        self._assistant_agent = AssistantAgent()
        self._chat_history_manager = ChatHistoryManager()

    async def evaluate_answer(
        self,
        image_path: Path,
        question_number: str,
        user_input: str,
        short_answers: list[str],
        full_answers: list[str],
        is_open_ended: bool,
        topic_name: str,
        rule: str | None = None,
    ) -> EvaluateAnswerOutput:
        """Evaluate if the user's answer is correct.

        Args:
            image_path: Path to the exercise image.
            question_number: The question number/ID.
            user_input: The user's answer.
            short_answers: All short answer variants.
            full_answers: All full answer variants.
            is_open_ended: Whether the question allows free-form responses.
            topic_name: The topic name for context.
            rule: Optional grammar rule for this question.

        Returns:
            EvaluateAnswerOutput with is_correct and answer_idx.
        """
        return await self._evaluate_agent.evaluate(
            image_path=image_path,
            question_number=question_number,
            user_input=user_input,
            short_answers=short_answers,
            full_answers=full_answers,
            is_open_ended=is_open_ended,
            topic_name=topic_name,
            rule=rule,
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
