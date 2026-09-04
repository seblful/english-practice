"""Assistant agent: answers a follow-up question about an exercise."""

from collections.abc import Sequence

from practice_runtime.agents import BaseAgent
from practice_runtime.tracing import traced

from practice_bot.models.agents import (
    AssistantContext,
    AssistantOutput,
    ChatMessage,
)


class AssistantAgent(BaseAgent):
    """Explains an exercise conversationally."""

    PROMPT_ANCHOR = "practice_bot.agents"
    PROMPT_TEMPLATE = "assistant.j2"

    @traced(name="assistant")
    async def assist(
        self,
        *,
        image: bytes | None,
        question_number: str,
        user_input: str,
        topic_name: str,
        chat_history: Sequence[ChatMessage] = (),
    ) -> AssistantOutput:
        """Answer the student's question about the current exercise."""
        context = AssistantContext(
            question_number=question_number,
            user_input=user_input,
            topic_name=topic_name,
            chat_history=list(chat_history),
        )

        return await self.invoke_structured(
            prompt=self.render(context),
            output_model=AssistantOutput,
            image=image,
        )
