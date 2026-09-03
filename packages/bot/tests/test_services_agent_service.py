"""Tests for the agent service."""

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from practice_core.models import Question, QuestionAnswer
from practice_runtime.errors import AgentError

from practice_bot.agents.evaluate import EvaluateAnswerAgent
from practice_bot.models.agents import (
    AssistantOutput,
    ChatMessage,
    EvaluateAnswerOutput,
)
from practice_bot.services.agent_service import AgentService


@dataclass
class Stubbed:
    """A service whose two agent calls are stubbed out."""

    service: AgentService
    evaluate: AsyncMock
    assist: AsyncMock

    def history(self) -> list[ChatMessage]:
        """Return the transcript passed to the most recent assistant call."""
        return list(_kwargs(self.assist)["chat_history"])

    def graded(self) -> dict[str, Any]:
        """Return the arguments passed to the most recent grading call."""
        return _kwargs(self.evaluate)


def _kwargs(mock: AsyncMock) -> dict[str, Any]:
    """Return the keyword arguments of a mock's most recent await."""
    call = mock.await_args
    assert call is not None
    return dict(call.kwargs)


def _stub(monkeypatch: pytest.MonkeyPatch, max_history_messages: int = 20) -> Stubbed:
    """Build a service with stubbed agents.

    Args:
        monkeypatch: Fixture used to replace the agent methods.
        max_history_messages: Transcript cap to configure.

    Returns:
        The service and the two stubs standing in for its agents.
    """
    service = AgentService(
        llm=Mock(spec=BaseChatModel), max_history_messages=max_history_messages
    )
    evaluate = AsyncMock(
        return_value=EvaluateAnswerOutput(is_correct=True, answer_idx=[0])
    )
    assist = AsyncMock(return_value=AssistantOutput(answer="because"))
    monkeypatch.setattr(service.grader, "evaluate", evaluate)
    monkeypatch.setattr(service._assistant_agent, "assist", assist)
    return Stubbed(service=service, evaluate=evaluate, assist=assist)


@pytest.fixture
def stubbed(monkeypatch: pytest.MonkeyPatch) -> Stubbed:
    """A service with stubbed agents."""
    return _stub(monkeypatch)


async def _ask(stubbed: Stubbed, question: str, exercise_id: int = 5) -> None:
    """Send one follow-up question through the service."""
    await stubbed.service.assist(
        user_id=1,
        exercise_id=exercise_id,
        image=None,
        question_number="1",
        user_input=question,
        topic_name="Present Tenses",
    )


class TestConstruction:
    """One client, shared by every agent."""

    def test_agents_share_the_injected_client(self) -> None:
        llm = Mock(spec=BaseChatModel)

        service = AgentService(llm=llm)

        assert service.grader.llm is llm
        assert service._assistant_agent.llm is llm

    def test_the_client_is_required(self) -> None:
        """Building one here would mean a connection pool per service."""
        with pytest.raises(TypeError):
            AgentService()  # ty: ignore[missing-argument]


class TestGrader:
    """The grading agent is handed out rather than wrapped."""

    def test_the_grader_shares_the_injected_client(self) -> None:
        """One connection pool per process, whichever agent is reached."""
        llm = Mock(spec=BaseChatModel)

        service = AgentService(llm=llm)

        assert isinstance(service.grader, EvaluateAnswerAgent)
        assert service.grader.llm is llm

    async def test_the_grader_is_the_agent_a_handler_calls(
        self, stubbed: Stubbed, answers: list[QuestionAnswer], question: Question
    ) -> None:
        """Nothing sits between the handler and the agent to restate its input."""
        result = await stubbed.service.grader.evaluate(
            question,
            user_input="is doing",
            answers=answers,
            topic_name="Present Tenses",
        )

        assert result.is_correct is True
        assert stubbed.graded()["answers"] == answers


class TestAssist:
    """Tests for the assistant and the transcript it maintains."""

    async def test_records_both_sides_of_the_exchange(self, stubbed: Stubbed) -> None:
        await _ask(stubbed, "why?")
        await _ask(stubbed, "and now?")

        assert [(m.role, m.content) for m in stubbed.history()] == [
            ("user", "why?"),
            ("assistant", "because"),
        ]

    async def test_transcript_starts_empty(self, stubbed: Stubbed) -> None:
        await _ask(stubbed, "why?")

        assert stubbed.history() == []

    async def test_starting_an_exercise_clears_older_transcripts(
        self, stubbed: Stubbed
    ) -> None:
        await _ask(stubbed, "why?", exercise_id=5)

        stubbed.service.start_exercise(1, 6)
        await _ask(stubbed, "new question", exercise_id=6)

        assert stubbed.history() == []

    async def test_a_failed_call_records_nothing(self, stubbed: Stubbed) -> None:
        """A retry must not see a half-recorded exchange."""
        stubbed.assist.side_effect = AgentError("provider down")

        with pytest.raises(AgentError):
            await _ask(stubbed, "why?")

        stubbed.assist.side_effect = None
        await _ask(stubbed, "why?")

        assert stubbed.history() == []

    async def test_forget_user_clears_the_transcript(self, stubbed: Stubbed) -> None:
        await _ask(stubbed, "why?")

        stubbed.service.forget_user(1)
        await _ask(stubbed, "again")

        assert stubbed.history() == []

    async def test_history_is_capped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stubbed = _stub(monkeypatch, max_history_messages=2)

        for _ in range(3):
            await _ask(stubbed, "why?")

        assert len(stubbed.history()) == 2
