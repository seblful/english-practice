"""End-to-end dispatch through a real Application.

These tests build the bot the way ``english-practice bot`` does — real handler
registration, real context type, real SQLite repository — and feed it real
:class:`telegram.Update` objects. Only the network edges are faked: the LLM
agents and the ``Bot`` that would talk to Telegram.

This is what catches the wiring mistakes unit tests cannot: a callback pattern
that matches no handler, a handler registered in the wrong order, a dependency
that never reached the context.
"""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from practice_core import content
from practice_runtime.settings import DashscopeSettings, LLMSettings, PathSettings
from pydantic import SecretStr
from telegram import CallbackQuery, Chat, Message, MessageEntity, Update, User
from telegram.ext import ExtBot

from practice_bot.app import BotApplication, build_application
from practice_bot.context import BotContext, BotDependencies
from practice_bot.models.agents import AssistantOutput, EvaluateAnswerOutput
from practice_bot.repositories.database import DatabaseRepository
from practice_bot.services.agent_service import AgentService
from practice_bot.settings import Settings, TelegramSettings
from practice_bot.states import SessionStore

pytestmark = pytest.mark.integration

CHAT_ID = 4242
USER = User(id=CHAT_ID, first_name="Test", is_bot=False, username="tester")
CHAT = Chat(id=CHAT_ID, type=Chat.PRIVATE)


@pytest.fixture
def fake_bot() -> AsyncMock:
    """A bot that records what would have been sent to Telegram."""
    bot = AsyncMock(spec=ExtBot)
    bot.defaults = None
    return bot


@pytest.fixture
def agents() -> AgentService:
    """An agent service whose LLM calls are stubbed."""
    service = AgentService(llm=Mock(spec=BaseChatModel))
    service._evaluate_agent.evaluate = AsyncMock(  # type: ignore[method-assign]
        return_value=EvaluateAnswerOutput(is_correct=True, answer_idx=[0])
    )
    service._assistant_agent.assist = AsyncMock(  # type: ignore[method-assign]
        return_value=AssistantOutput(answer="Because it is happening **now**.")
    )
    return service


@pytest.fixture
def application(
    seeded_db_path: Path, agents: AgentService, fake_bot: AsyncMock
) -> BotApplication:
    """The real application, wired to the seeded database."""
    settings = Settings(
        telegram=TelegramSettings(bot_token=SecretStr("123:abc"), admin_user_id=1),
        llm=LLMSettings(
            provider="dashscope",
            dashscope=DashscopeSettings(api_key=SecretStr("key")),
        ),
        paths=PathSettings(database_path=seeded_db_path),
    )
    dependencies = BotDependencies(
        repository=DatabaseRepository(seeded_db_path),
        agents=agents,
        sessions=SessionStore(),
        admin_user_id=None,
    )
    return build_application(settings, dependencies)


@pytest.fixture(autouse=True)
def _deterministic_draw(monkeypatch: pytest.MonkeyPatch) -> None:
    """Always draw the closed question, so these flows are deterministic.

    The seeded exercise carries one closed and one open-ended question, and
    which one a real draw picks would change what the bot replies.
    """
    # Replace the module reference inside the shared draw only: patching
    # random.choice itself would also hijack the formatter's phrase picker.
    monkeypatch.setattr(
        content,
        "random",
        SimpleNamespace(
            choice=lambda questions: next(
                question for question in questions if not question.is_open_ended
            )
        ),
    )


def _message(text: str, bot: AsyncMock, message_id: int = 1) -> Message:
    """Build an incoming message bound to the fake bot.

    Commands carry a bot-command entity, exactly as Telegram sends them: it is
    what tells ``CommandHandler`` the message is a command, and what keeps the
    catch-all text handler from swallowing it.
    """
    entities = (
        (
            MessageEntity(
                type=MessageEntity.BOT_COMMAND,
                offset=0,
                length=len(text.split(maxsplit=1)[0]),
            ),
        )
        if text.startswith("/")
        else ()
    )
    message = Message(
        message_id=message_id,
        date=datetime.now(UTC),
        chat=CHAT,
        from_user=USER,
        text=text,
        entities=entities,
    )
    message.set_bot(bot)
    return message


async def _dispatch(application: BotApplication, update: Update) -> None:
    """Route an update to the handler that claims it, error handler included.

    This mirrors what ``Application.process_update`` does, minus the network
    handshake that initialising a real ``Bot`` would need: registration order,
    the callback patterns and the custom context type are all the real ones.
    """
    context = BotContext.from_update(update, application)
    for handler in application.handlers[0]:
        check = handler.check_update(update)
        if check is None or check is False:
            continue
        try:
            await handler.handle_update(update, application, check, context)
        except Exception as exc:
            await application.process_error(update=update, error=exc)
        return
    raise AssertionError(f"no handler claimed {update}")


async def _send(application: BotApplication, bot: AsyncMock, text: str) -> None:
    """Dispatch a text message (or command) through the application."""
    await _dispatch(application, Update(update_id=1, message=_message(text, bot)))


async def _press(application: BotApplication, bot: AsyncMock, data: str) -> None:
    """Dispatch an inline-button press through the application."""
    query = CallbackQuery(
        id="q1",
        from_user=USER,
        chat_instance="ci",
        data=data,
        message=_message("previous", bot, message_id=2),
    )
    query.set_bot(bot)
    await _dispatch(application, Update(update_id=2, callback_query=query))


def _sent_text(bot: AsyncMock) -> list[str]:
    """Return the text of every message the bot was asked to send."""
    return [
        call.kwargs.get("text", "")
        for call in bot.send_message.await_args_list
        if call.kwargs.get("text")
    ]


def _sent_markup(bot: AsyncMock) -> list[Any]:
    """Return the keyboards attached to sent messages."""
    return [
        call.kwargs.get("reply_markup") for call in bot.send_message.await_args_list
    ]


class TestStartFlow:
    """From /start to an exercise on screen."""

    async def test_start_offers_the_menu(
        self, application: BotApplication, fake_bot: AsyncMock
    ) -> None:
        await _send(application, fake_bot, "/start")

        assert any("Welcome" in text for text in _sent_text(fake_bot))
        assert any(markup is not None for markup in _sent_markup(fake_bot))

    async def test_help_describes_the_commands(
        self, application: BotApplication, fake_bot: AsyncMock
    ) -> None:
        await _send(application, fake_bot, "/help")

        assert any("/exercise" in text for text in _sent_text(fake_bot))

    async def test_topic_button_sends_the_exercise_with_its_image(
        self, application: BotApplication, fake_bot: AsyncMock
    ) -> None:
        # Topic 1 has exactly one usable exercise, and it has a stored image.
        await _press(application, fake_bot, "topic:1")

        texts = _sent_text(fake_bot)
        assert any("Topic: <b>Present Tenses</b>" in text for text in texts)
        assert any("Answer question" in text for text in texts)
        fake_bot.send_photo.assert_awaited_once()

    async def test_random_button_draws_from_every_topic(
        self, application: BotApplication, fake_bot: AsyncMock
    ) -> None:
        await _press(application, fake_bot, "topic:random")

        texts = _sent_text(fake_bot)
        assert any("Topic:" in text for text in texts)
        assert any("Answer question" in text for text in texts)

    async def test_topic_list_button_lists_the_seeded_topics(
        self, application: BotApplication, fake_bot: AsyncMock
    ) -> None:
        await _press(application, fake_bot, "topic:new_topic")

        markup = next(m for m in _sent_markup(fake_bot) if m is not None)
        labels = [button.text for row in markup.inline_keyboard for button in row]
        assert labels == ["Past Tenses", "Present Tenses", "Unused Topic"]

    async def test_empty_topic_is_reported(
        self, application: BotApplication, fake_bot: AsyncMock
    ) -> None:
        await _press(application, fake_bot, "topic:3")

        assert any("No exercises found" in text for text in _sent_text(fake_bot))
        fake_bot.send_photo.assert_not_called()


class TestPracticeFlow:
    """Answering, then asking a follow-up question."""

    async def test_answer_is_graded_and_the_book_answer_revealed(
        self, application: BotApplication, fake_bot: AsyncMock
    ) -> None:
        await _press(application, fake_bot, "topic:1")
        fake_bot.reset_mock()

        await _send(application, fake_bot, "is doing")

        texts = _sent_text(fake_bot)
        assert any("✅" in text for text in texts)
        assert any("Correct Answer" in text for text in texts)
        assert texts[-1] == "Choose next exercise:"

    async def test_follow_up_question_reaches_the_assistant(
        self, application: BotApplication, fake_bot: AsyncMock, agents: AgentService
    ) -> None:
        await _press(application, fake_bot, "topic:1")
        await _send(application, fake_bot, "is doing")
        fake_bot.reset_mock()

        await _send(application, fake_bot, "why is it continuous?")

        assert any("Because it is happening" in t for t in _sent_text(fake_bot))

    async def test_show_unit_button_names_the_unit(
        self, application: BotApplication, fake_bot: AsyncMock
    ) -> None:
        await _press(application, fake_bot, "topic:1")
        fake_bot.reset_mock()

        await _press(application, fake_bot, "action:show_unit")

        assert any("Present Continuous" in text for text in _sent_text(fake_bot))

    async def test_rule_toggle_survives_to_the_next_answer(
        self, application: BotApplication, fake_bot: AsyncMock
    ) -> None:
        await _send(application, fake_bot, "/rule")
        await _press(application, fake_bot, "topic:1")
        fake_bot.reset_mock()

        await _send(application, fake_bot, "is doing")

        assert not any("Rule:" in text for text in _sent_text(fake_bot))

    async def test_message_without_an_exercise_points_at_start(
        self, application: BotApplication, fake_bot: AsyncMock
    ) -> None:
        await _send(application, fake_bot, "hello?")

        assert any("/start" in text for text in _sent_text(fake_bot))


class TestErrorHandling:
    """The application must survive a handler blowing up."""

    async def test_unexpected_failure_is_reported_to_the_user(
        self, application: BotApplication, fake_bot: AsyncMock, agents: AgentService
    ) -> None:
        await _press(application, fake_bot, "topic:1")
        agents._evaluate_agent.evaluate = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("not an AgentError")
        )
        fake_bot.reset_mock()

        await _send(application, fake_bot, "is doing")

        assert any("went wrong" in text for text in _sent_text(fake_bot))
