"""Orchestrates the LLM agents and the conversation state they need."""

from langchain_core.language_models.chat_models import BaseChatModel

from practice_bot.agents.assistant import AssistantAgent
from practice_bot.agents.evaluate import EvaluateAnswerAgent
from practice_bot.models.agents import AssistantOutput
from practice_bot.services.chat_history import (
    DEFAULT_MAX_MESSAGES,
    ChatHistoryManager,
)


class AgentService:
    """The application's single entry point to the LLM."""

    def __init__(
        self,
        llm: BaseChatModel,
        max_history_messages: int = DEFAULT_MAX_MESSAGES,
    ) -> None:
        """Initialize the service."""
        self._llm = llm
        self._evaluate_agent = EvaluateAnswerAgent(self._llm)
        self._assistant_agent = AssistantAgent(self._llm)
        self._history = ChatHistoryManager(max_messages=max_history_messages)

    @property
    def grader(self) -> EvaluateAnswerAgent:
        """The agent that grades an answer."""
        return self._evaluate_agent

    async def assist(
        self,
        *,
        user_id: int,
        exercise_id: int,
        image: bytes | None,
        question_number: str,
        user_input: str,
        topic_name: str,
    ) -> AssistantOutput:
        """Answer a follow-up question, recording both sides of the exchange."""
        result = await self._assistant_agent.assist(
            image=image,
            question_number=question_number,
            user_input=user_input,
            topic_name=topic_name,
            chat_history=self._history.history(user_id, exercise_id),
        )

        self._history.add_turn(user_id, exercise_id, "user", user_input)
        self._history.add_turn(user_id, exercise_id, "assistant", result.answer)

        return result

    def start_exercise(self, user_id: int, exercise_id: int) -> None:
        """Drop transcripts for exercises the user has moved on from."""
        self._history.start_exercise(user_id, exercise_id)

    def forget_user(self, user_id: int) -> None:
        """Drop every transcript stored for one user."""
        self._history.forget_user(user_id)
