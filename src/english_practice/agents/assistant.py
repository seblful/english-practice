"""Assistant Agent - conversational helper with history."""

from pathlib import Path
from typing import TYPE_CHECKING

from langsmith import traceable

from src.english_practice.agents.base import BaseAgent
from src.english_practice.models.agents import (
    AssistantContext,
    AssistantOutput,
    ChatMessage,
)

if TYPE_CHECKING:
    from src.english_practice.services.chat_history import ChatHistoryManager


class AssistantAgent(BaseAgent):
    """Agent for conversational assistance with chat history."""

    PROMPT_TEMPLATE = "assistant.j2"

    @traceable(name="assistant")
    async def assist(
        self,
        user_id: int,
        image_path: Path,
        question_number: str,
        user_input: str,
        topic_name: str,
        chat_history_manager: "ChatHistoryManager",
    ) -> AssistantOutput:
        """Provide conversational assistance based on chat history.

        Args:
            user_id: The user's ID for history tracking.
            image_path: Path to the exercise image.
            question_number: The question number/ID.
            user_input: The user's question or message.
            topic_name: The topic name for context.
            chat_history_manager: Chat history manager instance.

        Returns:
            AssistantOutput with response.
        """
        raw_history = chat_history_manager.get_history(user_id, image_path)
        chat_history = [ChatMessage(**msg) for msg in raw_history]

        context = AssistantContext(
            question_number=question_number,
            user_input=user_input,
            topic_name=topic_name,
            chat_history=chat_history,
        )
        prompt = self.render(context)

        result = await self.invoke_structured(
            prompt=prompt,
            output_model=AssistantOutput,
            image_path=image_path,
        )

        chat_history_manager.add_message(
            user_id=user_id,
            image_path=image_path,
            role="user",
            content=user_input,
        )
        chat_history_manager.add_message(
            user_id=user_id,
            image_path=image_path,
            role="assistant",
            content=result.answer,
        )

        return result

    def on_new_image(
        self,
        user_id: int,
        new_image_path: Path,
        chat_history_manager: "ChatHistoryManager",
    ) -> None:
        """Handle new image - clear history for all other images of this user.

        Args:
            user_id: The user's ID.
            new_image_path: Path to the new exercise image.
            chat_history_manager: Chat history manager instance.
        """
        chat_history_manager.on_new_image(user_id, new_image_path)
