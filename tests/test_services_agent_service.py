"""Tests for the agent service."""

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.language_models.chat_models import BaseChatModel

from english_practice.errors import AgentError
from english_practice.models.agents import (
    AssistantOutput,
    ChatMessage,
    EvaluateAnswerOutput,
)
from english_practice.models.book import QuestionAnswer
from english_practice.services.agent_service import AgentService


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
    monkeypatch.setattr(service._evaluate_agent, "evaluate", evaluate)
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
        image_data=None,
        question_number="1",
        user_input=question,
        topic_name="Present Tenses",
    )


class TestConstruction:
    """One client, shared by every agent."""

    def test_agents_share_the_injected_client(self) -> None:
        llm = Mock(spec=BaseChatModel)

        service = AgentService(llm=llm)

        assert service._evaluate_agent.llm is llm
        assert service._assistant_agent.llm is llm

    def test_builds_a_client_from_settings_when_none_is_given(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        llm = Mock(spec=BaseChatModel)
        monkeypatch.setattr(
            "english_practice.services.agent_service.get_llm", lambda: llm
        )

        assert AgentService()._evaluate_agent.llm is llm


class TestEvaluateAnswer:
    """Tests for grading."""

    async def test_splits_answers_into_the_prompt_lists(
        self, stubbed: Stubbed, answers: list[QuestionAnswer]
    ) -> None:
        await stubbed.service.evaluate_answer(
            image_data=b"png",
            question_number="1",
            user_input="is doing",
            answers=answers,
            is_open_ended=False,
            topic_name="Present Tenses",
            rule="a rule",
        )

        kwargs = stubbed.graded()
        assert kwargs["short_answers"] == ["is doing", "'s doing"]
        assert kwargs["full_answers"] == [
            "He **is doing** his homework.",
            "He **'s doing** his homework.",
        ]
        assert kwargs["rule"] == "a rule"

    async def test_returns_the_verdict(
        self, stubbed: Stubbed, answers: list[QuestionAnswer]
    ) -> None:
        result = await stubbed.service.evaluate_answer(
            image_data=None,
            question_number="1",
            user_input="is doing",
            answers=answers,
            is_open_ended=False,
            topic_name="Present Tenses",
        )

        assert result.is_correct is True
        assert result.answer_idx == [0]

    async def test_question_without_answers(self, stubbed: Stubbed) -> None:
        await stubbed.service.evaluate_answer(
            image_data=None,
            question_number="1",
            user_input="anything",
            answers=[],
            is_open_ended=True,
            topic_name="Present Tenses",
        )

        kwargs = stubbed.graded()
        assert kwargs["short_answers"] == []
        assert kwargs["is_open_ended"] is True


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
