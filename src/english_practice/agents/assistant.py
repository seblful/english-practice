"""Assistant agent: answers a follow-up question about an exercise."""

from collections.abc import Sequence

from english_practice.agents.base import BaseAgent
from english_practice.agents.tracing import traced
from english_practice.models.agents import (
    AssistantContext,
    AssistantOutput,
    ChatMessage,
)


class AssistantAgent(BaseAgent):
    """Explains an exercise conversationally.

    The transcript is passed in rather than looked up: keeping this agent a
    pure prompt-and-parse call leaves conversation state to the service that
    owns it.
    """

    PROMPT_TEMPLATE = "assistant.j2"

    @traced(name="assistant")
    async def assist(
        self,
        *,
        image_data: bytes | None,
        question_number: str,
        user_input: str,
        topic_name: str,
        chat_history: Sequence[ChatMessage] = (),
    ) -> AssistantOutput:
        """Answer the student's question about the current exercise.

        Args:
            image_data: Raw exercise image bytes, if the exercise has one.
            question_number: The question number/ID.
            user_input: The student's question.
            topic_name: The topic name, for context.
            chat_history: Earlier turns about this exercise, oldest first.

        Returns:
            The assistant's answer.

        Raises:
            AgentError: If the LLM call fails or cannot be parsed.
        """
        context = AssistantContext(
            question_number=question_number,
            user_input=user_input,
            topic_name=topic_name,
            chat_history=list(chat_history),
        )

        return await self.invoke_structured(
            prompt=self.render(context),
            output_model=AssistantOutput,
            image_data=image_data,
        )
