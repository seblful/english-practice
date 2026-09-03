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
    """The application's single entry point to the LLM.

    Holds one chat-model client, shares it between agents, and owns the
    assistant transcripts so the agents stay stateless. Build one per process:
    each client carries its own HTTP connection pool.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        max_history_messages: int = DEFAULT_MAX_MESSAGES,
    ) -> None:
        """Initialize the service.

        Args:
            llm: Chat model shared by every agent. Built once by the caller
                that owns the process, so that one connection pool serves
                every message.
            max_history_messages: Assistant turns kept per exercise.
        """
        self._llm = llm
        self._evaluate_agent = EvaluateAnswerAgent(self._llm)
        self._assistant_agent = AssistantAgent(self._llm)
        self._history = ChatHistoryManager(max_messages=max_history_messages)

    @property
    def grader(self) -> EvaluateAnswerAgent:
        """The agent that grades an answer.

        Handed out rather than wrapped. Wrapping it meant restating its
        seven-field interface here, which put the same parameter list in four
        files between the handler and the prompt -- and this class made no
        decision about any of them. What it does own is below: the assistant's
        transcripts, which is why ``assist`` is a method and this is not.
        """
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
        """Answer a follow-up question, recording both sides of the exchange.

        Args:
            user_id: The user's Telegram ID.
            exercise_id: Exercise the conversation is about.
            image: Raw exercise image bytes, if the exercise has one.
            question_number: The question number/ID.
            user_input: The student's question.
            topic_name: The topic name, for context.

        Returns:
            The assistant's answer.

        Raises:
            AgentError: If the LLM call fails or cannot be parsed. Nothing is
                recorded in that case, so a retry sees the same history.
        """
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
        """Drop transcripts for exercises the user has moved on from.

        Args:
            user_id: The user's Telegram ID.
            exercise_id: The exercise the user just started.
        """
        self._history.start_exercise(user_id, exercise_id)

    def forget_user(self, user_id: int) -> None:
        """Drop every transcript stored for one user.

        Args:
            user_id: The user's Telegram ID.
        """
        self._history.forget_user(user_id)
