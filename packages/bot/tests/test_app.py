"""Tests for application assembly."""

import os
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from practice_runtime.errors import ConfigurationError
from practice_runtime.settings import (
    DashscopeSettings,
    LangSmithSettings,
    LLMSettings,
    PathSettings,
)
from pydantic import SecretStr
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler

from practice_bot import commands
from practice_bot.app import (
    _prepare,
    build_application,
    build_dependencies,
    configure_tracing,
    run,
)
from practice_bot.context import BotContext, BotDependencies, install_dependencies
from practice_bot.handlers import build_handlers
from practice_bot.settings import Settings, TelegramSettings


@pytest.fixture
def runnable_settings(tmp_path: Path) -> Settings:
    """Settings that satisfy every startup requirement."""
    database = tmp_path / "english_practice.db"
    database.touch()
    return Settings(
        telegram=TelegramSettings(bot_token=SecretStr("123:abc"), admin_user_id=7),
        llm=LLMSettings(
            provider="dashscope",
            dashscope=DashscopeSettings(api_key=SecretStr("key")),
        ),
        paths=PathSettings(database_path=database),
    )


@pytest.fixture
def stub_dependencies(dependencies: BotDependencies) -> BotDependencies:
    """The mock dependencies, so no client or database is really built."""
    return dependencies


class TestBuildApplication:
    """Tests for wiring the application together."""

    def test_registers_every_handler_and_the_error_handler(
        self, runnable_settings: Settings, stub_dependencies: BotDependencies
    ) -> None:
        application = build_application(runnable_settings, stub_dependencies)

        registered = application.handlers[0]
        assert len(registered) == len(build_handlers())
        assert application.error_handlers

    def test_installs_dependencies_for_handlers(
        self, runnable_settings: Settings, stub_dependencies: BotDependencies
    ) -> None:
        application = build_application(runnable_settings, stub_dependencies)

        context = BotContext(application=application)
        assert context.dependencies is stub_dependencies
        assert context.repository is stub_dependencies.repository

    def test_uses_the_custom_context_type(
        self, runnable_settings: Settings, stub_dependencies: BotDependencies
    ) -> None:
        application = build_application(runnable_settings, stub_dependencies)

        assert application.context_types.context is BotContext

    def test_dispatch_order_puts_the_catch_all_last(self) -> None:
        handlers = build_handlers()

        assert isinstance(handlers[0], CommandHandler)
        assert isinstance(handlers[-1], MessageHandler)
        assert any(isinstance(h, CallbackQueryHandler) for h in handlers)

    def test_missing_settings_stop_the_build(
        self, runnable_settings: Settings, stub_dependencies: BotDependencies
    ) -> None:
        runnable_settings.telegram.bot_token = None

        with pytest.raises(ConfigurationError, match="TELEGRAM_BOT_TOKEN"):
            build_application(runnable_settings, stub_dependencies)

    def test_missing_database_stops_the_build(
        self, runnable_settings: Settings, stub_dependencies: BotDependencies
    ) -> None:
        runnable_settings.paths.database_path = Path("nowhere/absent.db")

        with pytest.raises(ConfigurationError, match="database not found"):
            build_application(runnable_settings, stub_dependencies)


class TestBuildDependencies:
    """Tests for building the collaborators from settings."""

    def test_wires_settings_into_the_dependencies(
        self, runnable_settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "practice_bot.app.get_llm",
            lambda _config: Mock(spec=BaseChatModel),
        )

        dependencies = build_dependencies(runnable_settings)

        assert dependencies.admin_user_id == 7
        assert dependencies.repository.db_path == runnable_settings.paths.database_path
        assert dependencies.access_control_enabled is True


class TestConfigureTracing:
    """Tests for exporting the LangSmith variables."""

    def test_exports_when_a_key_is_configured(
        self, runnable_settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for name in ("LANGSMITH_API_KEY", "LANGSMITH_PROJECT", "LANGSMITH_TRACING"):
            monkeypatch.delenv(name, raising=False)
        runnable_settings.langsmith = LangSmithSettings(
            api_key=SecretStr("ls-key"), project="proj", tracing=True
        )

        configure_tracing(runnable_settings)

        assert os.environ["LANGSMITH_API_KEY"] == "ls-key"
        assert os.environ["LANGSMITH_PROJECT"] == "proj"
        assert os.environ["LANGSMITH_TRACING"] == "true"

    def test_exports_nothing_without_a_key(
        self, runnable_settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("LANGSMITH_PROJECT", raising=False)
        runnable_settings.langsmith = LangSmithSettings(api_key=None)

        configure_tracing(runnable_settings)

        assert "LANGSMITH_PROJECT" not in os.environ


class TestPrepare:
    """Tests for what happens once, before the first update."""

    def _application(self, dependencies: BotDependencies) -> Mock:
        """An application with the dependencies installed, as `app` builds it."""
        application = Mock(bot=AsyncMock(), bot_data={})
        install_dependencies(application.bot_data, dependencies)
        return application

    async def test_registers_commands_and_the_menu_button(
        self, stub_dependencies: BotDependencies
    ) -> None:
        application = self._application(stub_dependencies)

        await _prepare(application)

        published = application.bot.set_my_commands.await_args.args[0]
        assert [entry.command for entry in published] == [
            command.name for command in commands.COMMANDS
        ]
        application.bot.set_chat_menu_button.assert_awaited_once()

    async def test_creates_the_bot_own_tables(
        self, stub_dependencies: BotDependencies, mock_repository: AsyncMock
    ) -> None:
        """The pipeline builds the content tables; `authorized_users` is ours."""
        application = self._application(stub_dependencies)

        await _prepare(application)

        mock_repository.ensure_schema.assert_awaited_once()


class TestRun:
    """Tests for starting the bot."""

    def test_polls_with_the_configured_update_types(
        self,
        runnable_settings: Settings,
        stub_dependencies: BotDependencies,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        application = Mock()
        monkeypatch.setattr(
            "practice_bot.app.build_application", lambda _settings: application
        )

        run(runnable_settings)

        kwargs = application.run_polling.call_args.kwargs
        assert kwargs["allowed_updates"] == runnable_settings.telegram.allowed_updates
        assert kwargs["close_loop"] is runnable_settings.telegram.close_loop

    def test_defaults_to_the_process_settings(
        self,
        runnable_settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        application = Mock()
        monkeypatch.setattr("practice_bot.app.get_settings", lambda: runnable_settings)
        monkeypatch.setattr(
            "practice_bot.app.build_application", lambda _settings: application
        )

        run()

        application.run_polling.assert_called_once()
