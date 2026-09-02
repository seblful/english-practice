"""Tests for the bot's models: its LLM calls, and who may use it."""

import pytest
from practice_core.models import QuestionAnswer
from pydantic import ValidationError

from practice_bot.models.agents import (
    AssistantContext,
    AssistantOutput,
    ChatMessage,
    EvaluateAnswerInput,
    EvaluateAnswerOutput,
)
from practice_bot.models.auth import PendingUser


class TestEvaluateAnswerInput:
    """The shared grading context, re-exported here for the handlers."""

    def test_minimal_fields(self) -> None:
        model = EvaluateAnswerInput(
            question_number="1",
            user_input="my answer",
            answers=[QuestionAnswer(short_answer="a", full_answer="b")],
            is_open_ended=False,
            topic_name="Test",
        )

        assert model.question_number == "1"
        assert model.rule is None

    def test_with_rule(self) -> None:
        model = EvaluateAnswerInput(
            question_number="2",
            user_input="answer",
            answers=[QuestionAnswer(short_answer="a", full_answer="b")],
            is_open_ended=False,
            topic_name="Test",
            rule="Use present tense",
        )

        assert model.rule == "Use present tense"


class TestEvaluateAnswerOutput:
    def test_correct_with_indexes(self) -> None:
        model = EvaluateAnswerOutput(is_correct=True, answer_idx=[0, 2])

        assert model.is_correct is True
        assert model.answer_idx == [0, 2]

    def test_incorrect_empty_indexes(self) -> None:
        model = EvaluateAnswerOutput(is_correct=False)

        assert model.is_correct is False
        assert model.answer_idx == []


class TestChatMessage:
    def test_fields(self) -> None:
        msg = ChatMessage(role="user", content="hello")

        assert msg.role == "user"
        assert msg.content == "hello"

    def test_only_the_two_roles_a_transcript_has(self) -> None:
        with pytest.raises(ValidationError):
            ChatMessage.model_validate({"role": "system", "content": "hello"})


class TestAssistantContext:
    def test_minimal(self) -> None:
        ctx = AssistantContext(
            question_number="1", user_input="help", topic_name="Test"
        )

        assert ctx.chat_history == []

    def test_with_history(self) -> None:
        history = [ChatMessage(role="user", content="hi")]

        ctx = AssistantContext(
            question_number="1",
            user_input="help",
            topic_name="Test",
            chat_history=history,
        )

        assert len(ctx.chat_history) == 1


class TestAssistantOutput:
    def test_fields(self) -> None:
        assert AssistantOutput(answer="Here is help").answer == "Here is help"


class TestPendingUser:
    """The access-request model — the one content model that is the bot's own."""

    def test_label_includes_the_username(self) -> None:
        user = PendingUser(telegram_id=1, full_name="Alice", telegram_username="alice")

        assert user.label == "Alice (@alice)"

    def test_label_without_a_username(self) -> None:
        assert PendingUser(telegram_id=1, full_name="Alice").label == "Alice"
