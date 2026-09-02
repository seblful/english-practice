"""Orchestrates the LLM agents and the conversation state they need."""

from collections.abc import Sequence

from langchain_core.language_models.chat_models import BaseChatModel

from english_practice.agents.assistant import AssistantAgent
from english_practice.agents.evaluate import EvaluateAnswerAgent
from english_practice.llm import get_llm
from english_practice.models.agents import AssistantOutput, EvaluateAnswerOutput
from english_practice.models.book import QuestionAnswer
from english_practice.services.chat_history import (
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
        llm: BaseChatModel | None = None,
        max_history_messages: int = DEFAULT_MAX_MESSAGES,
    ) -> None:
        """Initialize the service.

        Args:
            llm: Chat model shared by every agent. Built from settings when
                omitted, which requires the provider's API key.
            max_history_messages: Assistant turns kept per exercise.
        """
        self._llm = llm or get_llm()
        self._evaluate_agent = EvaluateAnswerAgent(self._llm)
        self._assistant_agent = AssistantAgent(self._llm)
        self._history = ChatHistoryManager(max_messages=max_history_messages)

    async def evaluate_answer(
        self,
        *,
        image_data: bytes | None,
        question_number: str,
        user_input: str,
        answers: Sequence[QuestionAnswer],
        is_open_ended: bool,
        topic_name: str,
        rule: str | None = None,
    ) -> EvaluateAnswerOutput:
        """Grade the student's answer for one question.

        Args:
            image_data: Raw exercise image bytes, if the exercise has one.
            question_number: The question number/ID.
            user_input: The student's answer.
            answers: Expected answers in display order; ``answer_idx`` in the
                result indexes into this sequence.
            is_open_ended: Whether the question allows free-form responses.
            topic_name: The topic name, for context.
            rule: The grammar rule for this question, when known.

        Returns:
            Whether the answer is correct, and which expected answers matched.

        Raises:
            AgentError: If the LLM call fails or cannot be parsed.
        """
        return await self._evaluate_agent.evaluate(
            image_data=image_data,
            question_number=question_number,
            user_input=user_input,
            answers=answers,
            is_open_ended=is_open_ended,
            topic_name=topic_name,
            rule=rule,
        )

    async def assist(
        self,
        *,
        user_id: int,
        exercise_id: int,
        image_data: bytes | None,
        question_number: str,
        user_input: str,
        topic_name: str,
    ) -> AssistantOutput:
        """Answer a follow-up question, recording both sides of the exchange.

        Args:
            user_id: The user's Telegram ID.
            exercise_id: Exercise the conversation is about.
            image_data: Raw exercise image bytes, if the exercise has one.
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
            image_data=image_data,
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
