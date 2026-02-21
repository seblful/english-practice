"""Assistant Agent - conversational helper with history."""

from pathlib import Path
from typing import TYPE_CHECKING

from langsmith import traceable

from src.english_practice.agents.base import BaseAgent
from src.english_practice.models.agents import AssistantOutput
from src.english_practice.models.constants import PROMPT_ASSISTANT

if TYPE_CHECKING:
    from src.english_practice.services.chat_history import ChatHistoryManager


class AssistantAgent(BaseAgent):
    """Agent for conversational assistance with chat history."""

    @traceable(name="assistant")
    def assist(
        self,
        user_id: int,
        image_path: Path,
        question_number: str,
        user_input: str,
        chat_history_manager: "ChatHistoryManager",
    ) -> AssistantOutput:
        """Provide conversational assistance based on chat history.

        Args:
            user_id: The user's ID for history tracking.
            image_path: Path to the exercise image.
            question_number: The question number/ID.
            user_input: The user's question or message.
            chat_history_manager: Chat history manager instance.

        Returns:
            AssistantOutput with response.
        """
        # Get chat history for this user and image
        chat_history = chat_history_manager.get_history(user_id, image_path)

        prompt = self.render_agent_prompt(
            PROMPT_ASSISTANT,
            chat_history=chat_history,
            question_number=question_number,
            user_input=user_input,
        )

        result = self.invoke_structured(
            prompt=prompt,
            output_model=AssistantOutput,
            image_path=image_path,
        )

        # Add user message and assistant response to history
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
